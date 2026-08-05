"""Core AcroForm designer operations shared by the GUI and tests.

This module intentionally depends only on PyMuPDF so structural form operations
can be verified without launching Qt. Low-level PDF editing is isolated to the
radio-group helper because PyMuPDF's high-level API cannot create interconnected
radio button groups.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

import fitz


DEFAULT_TEXT_SIZE = (180.0, 26.0)
DEFAULT_DROPDOWN_SIZE = (180.0, 26.0)
DEFAULT_DATE_SIZE = (130.0, 26.0)
DEFAULT_SIGNATURE_SIZE = (200.0, 60.0)
DEFAULT_INITIALS_SIZE = (85.0, 42.0)
DEFAULT_RADIO_GROUP_SIZE = (70.0, 20.0)
DEFAULT_CHECKBOX_SIZE = 20.0
MIN_TEXT_SIZE = (50.0, 18.0)
MIN_CHOICE_SIZE = (70.0, 18.0)
MIN_SIGNATURE_SIZE = (70.0, 30.0)
MIN_CHECKBOX_SIZE = 12.0

PDF_STUDIO_KIND_KEY = "PDFStudioKind"
PDF_STUDIO_OPTION_KEY = "PDFStudioOption"
KIND_DATE = "Date"
KIND_INITIALS = "Initials"
KIND_RADIO_GROUP = "RadioGroup"


def iter_widgets(document: fitz.Document) -> Iterable[tuple[int, fitz.Widget]]:
    """Yield ``(page_number, widget)`` pairs for every AcroForm field."""
    for page_number in range(document.page_count):
        page = document.load_page(page_number)
        for widget in page.widgets() or []:
            yield page_number, widget


def existing_field_names(document: fitz.Document) -> set[str]:
    return {
        str(widget.field_name)
        for _page_number, widget in iter_widgets(document)
        if getattr(widget, "field_name", None)
    }


def unique_field_name(document: fitz.Document, prefix: str) -> str:
    """Return a stable, human-readable field name not already in the PDF."""
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", prefix.strip()).strip("_") or "field"
    names = existing_field_names(document)
    if safe not in names:
        return safe
    index = 2
    while f"{safe}_{index}" in names:
        index += 1
    return f"{safe}_{index}"


def normalise_rect(
    rect: fitz.Rect,
    page_rect: fitz.Rect,
    *,
    min_width: float,
    min_height: float,
) -> fitz.Rect:
    """Normalise, constrain, and enforce a useful minimum field rectangle."""
    candidate = fitz.Rect(rect)
    candidate.normalize()

    width = min(page_rect.width, max(float(min_width), candidate.width))
    height = min(page_rect.height, max(float(min_height), candidate.height))
    x0 = max(page_rect.x0, min(candidate.x0, page_rect.x1 - width))
    y0 = max(page_rect.y0, min(candidate.y0, page_rect.y1 - height))
    x1 = min(page_rect.x1, x0 + width)
    y1 = min(page_rect.y1, y0 + height)

    x0 = max(page_rect.x0, min(x0, x1))
    y0 = max(page_rect.y0, min(y0, y1))
    return fitz.Rect(x0, y0, x1, y1)


def _last_widget(page: fitz.Page, xref: int | None = None) -> fitz.Widget:
    widgets = list(page.widgets() or [])
    if xref is not None:
        for widget in widgets:
            if int(widget.xref) == int(xref):
                return widget
    if not widgets:
        raise RuntimeError("PyMuPDF did not create the requested form field.")
    return widgets[-1]


def _style_box_widget(widget: fitz.Widget) -> None:
    widget.fill_color = (1.0, 1.0, 1.0)
    widget.border_color = (0.18, 0.42, 0.72)
    widget.border_width = 1


def add_text_field(
    document: fitz.Document,
    page_number: int,
    rect: fitz.Rect,
    *,
    name: str | None = None,
    multiline: bool = False,
) -> fitz.Widget:
    page = document.load_page(page_number)
    rect = normalise_rect(
        rect,
        page.rect,
        min_width=MIN_TEXT_SIZE[0],
        min_height=MIN_TEXT_SIZE[1],
    )

    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_name = name or unique_field_name(document, "text_field")
    widget.field_label = widget.field_name
    widget.field_value = ""
    widget.field_value_default = ""
    widget.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE if multiline else 0
    widget.rect = rect
    widget.text_font = "Helv"
    widget.text_fontsize = 11
    widget.text_color = (0.0, 0.0, 0.0)
    _style_box_widget(widget)
    annotation = page.add_widget(widget)
    return _last_widget(page, int(annotation.xref))


def add_date_field(
    document: fitz.Document,
    page_number: int,
    rect: fitz.Rect,
    *,
    name: str | None = None,
) -> fitz.Widget:
    """Create a portable date-entry text field without embedded JavaScript."""
    page = document.load_page(page_number)
    rect = normalise_rect(
        rect,
        page.rect,
        min_width=MIN_CHOICE_SIZE[0],
        min_height=MIN_CHOICE_SIZE[1],
    )
    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_name = name or unique_field_name(document, "date_field")
    widget.field_label = "Date (DD/MM/YYYY)"
    widget.field_value = ""
    widget.field_value_default = ""
    widget.text_maxlen = 10
    widget.rect = rect
    widget.text_font = "Helv"
    widget.text_fontsize = 11
    widget.text_color = (0.0, 0.0, 0.0)
    _style_box_widget(widget)
    annotation = page.add_widget(widget)
    xref = int(annotation.xref)
    document.xref_set_key(xref, PDF_STUDIO_KIND_KEY, f"/{KIND_DATE}")
    return _last_widget(page, xref)


def add_dropdown_field(
    document: fitz.Document,
    page_number: int,
    rect: fitz.Rect,
    *,
    name: str | None = None,
    choices: Sequence[str] | None = None,
    editable: bool = False,
) -> fitz.Widget:
    page = document.load_page(page_number)
    rect = normalise_rect(
        rect,
        page.rect,
        min_width=MIN_CHOICE_SIZE[0],
        min_height=MIN_CHOICE_SIZE[1],
    )
    values = _normalise_choices(choices or ("", "Option 1", "Option 2"))

    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
    widget.field_name = name or unique_field_name(document, "dropdown")
    widget.field_label = widget.field_name
    widget.choice_values = values
    widget.field_value = values[0]
    widget.field_value_default = values[0]
    widget.field_flags = fitz.PDF_CH_FIELD_IS_EDIT if editable else 0
    widget.rect = rect
    widget.text_font = "Helv"
    widget.text_fontsize = 11
    widget.text_color = (0.0, 0.0, 0.0)
    _style_box_widget(widget)
    annotation = page.add_widget(widget)
    return _last_widget(page, int(annotation.xref))


def add_checkbox_field(
    document: fitz.Document,
    page_number: int,
    rect: fitz.Rect,
    *,
    name: str | None = None,
) -> fitz.Widget:
    page = document.load_page(page_number)
    source = fitz.Rect(rect)
    source.normalize()
    square = max(MIN_CHECKBOX_SIZE, min(source.width, source.height))
    candidate = fitz.Rect(
        source.x0, source.y0, source.x0 + square, source.y0 + square
    )
    candidate = normalise_rect(
        candidate,
        page.rect,
        min_width=MIN_CHECKBOX_SIZE,
        min_height=MIN_CHECKBOX_SIZE,
    )

    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    widget.field_name = name or unique_field_name(document, "checkbox")
    widget.field_label = widget.field_name
    widget.field_value = False
    widget.field_value_default = False
    widget.rect = candidate
    widget.text_font = "ZaDb"
    widget.text_fontsize = 0
    _style_box_widget(widget)
    annotation = page.add_widget(widget)
    return _last_widget(page, int(annotation.xref))


def add_signature_field(
    document: fitz.Document,
    page_number: int,
    rect: fitz.Rect,
    *,
    name: str | None = None,
    initials: bool = False,
) -> fitz.Widget:
    """Create a genuine unsigned PDF signature field.

    PDF Studio detects and preserves the field but does not perform
    certificate-backed signing itself.
    """
    page = document.load_page(page_number)
    rect = normalise_rect(
        rect,
        page.rect,
        min_width=MIN_SIGNATURE_SIZE[0],
        min_height=MIN_SIGNATURE_SIZE[1],
    )
    prefix = "initials" if initials else "signature"
    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    widget.field_name = name or unique_field_name(document, prefix)
    widget.field_label = "Initials" if initials else "Signature"
    widget.rect = rect
    _style_box_widget(widget)
    annotation = page.add_widget(widget)
    xref = int(annotation.xref)
    if initials:
        document.xref_set_key(xref, PDF_STUDIO_KIND_KEY, f"/{KIND_INITIALS}")
    return _last_widget(page, xref)


def _pdf_name(value: str, fallback: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_.-")
    return name or fallback


def _acroform_fields_owner(document: fitz.Document) -> tuple[int, str] | None:
    catalog = document.pdf_catalog()
    value_type, value = document.xref_get_key(catalog, "AcroForm")
    if value_type == "xref":
        return int(value.split()[0]), "Fields"
    if value_type == "dict":
        return catalog, "AcroForm/Fields"
    return None


def _top_level_field_refs(document: fitz.Document) -> list[int]:
    owner = _acroform_fields_owner(document)
    if owner is None:
        return []
    value_type, value = document.xref_get_key(owner[0], owner[1])
    if value_type != "array":
        return []
    return [int(match) for match in re.findall(r"(\d+)\s+0\s+R", value)]


def _set_top_level_field_refs(document: fitz.Document, refs: Sequence[int]) -> None:
    owner = _acroform_fields_owner(document)
    if owner is None:
        raise RuntimeError("The PDF AcroForm dictionary was not created.")
    value = "[ " + " ".join(f"{int(xref)} 0 R" for xref in refs) + " ]"
    document.xref_set_key(owner[0], owner[1], value)


def _replace_button_on_state(
    document: fitz.Document,
    widget_xref: int,
    new_state: str,
) -> None:
    value_type, appearance = document.xref_get_key(widget_xref, "AP/N")
    if value_type != "dict":
        raise RuntimeError("Radio button appearance dictionary is missing.")
    pairs = re.findall(r"/([^\s/<>{}\[\]()]+)\s+(\d+\s+0\s+R)", appearance)
    off_ref = next((ref for key, ref in pairs if key == "Off"), None)
    on_ref = next((ref for key, ref in pairs if key != "Off"), None)
    if off_ref is None or on_ref is None:
        raise RuntimeError("Radio button appearance states are incomplete.")
    document.xref_set_key(
        widget_xref,
        "AP/N",
        f"<< /Off {off_ref} /{new_state} {on_ref} >>",
    )


def add_radio_group(
    document: fitz.Document,
    page_number: int,
    rect: fitz.Rect,
    *,
    name: str | None = None,
    label: str = "Yes / No",
    options: Sequence[str] = ("Yes", "No"),
) -> list[fitz.Widget]:
    """Create an interconnected radio group using a standards-based parent field."""
    clean_options = [str(option).strip() for option in options if str(option).strip()]
    if len(clean_options) < 2:
        raise ValueError("A radio group requires at least two options.")
    state_names: list[str] = []
    for index, option in enumerate(clean_options, 1):
        state = _pdf_name(option, f"Option{index}")
        base = state
        suffix = 2
        while state in state_names or state == "Off":
            state = f"{base}_{suffix}"
            suffix += 1
        state_names.append(state)

    page = document.load_page(page_number)
    group_rect = normalise_rect(
        rect,
        page.rect,
        min_width=MIN_CHECKBOX_SIZE * len(clean_options),
        min_height=MIN_CHECKBOX_SIZE,
    )
    horizontal = group_rect.width >= group_rect.height
    square = max(
        MIN_CHECKBOX_SIZE,
        min(
            DEFAULT_CHECKBOX_SIZE,
            group_rect.height if horizontal else group_rect.width,
        ),
    )
    if horizontal:
        span = max(0.0, group_rect.width - square)
        positions = [
            fitz.Rect(
                group_rect.x0 + (span * index / (len(clean_options) - 1)),
                group_rect.y0,
                group_rect.x0 + (span * index / (len(clean_options) - 1)) + square,
                group_rect.y0 + square,
            )
            for index in range(len(clean_options))
        ]
    else:
        span = max(0.0, group_rect.height - square)
        positions = [
            fitz.Rect(
                group_rect.x0,
                group_rect.y0 + (span * index / (len(clean_options) - 1)),
                group_rect.x0 + square,
                group_rect.y0 + (span * index / (len(clean_options) - 1)) + square,
            )
            for index in range(len(clean_options))
        ]

    group_name = name or unique_field_name(document, "yes_no")
    child_xrefs: list[int] = []
    for index, (option, state, position) in enumerate(
        zip(clean_options, state_names, positions), 1
    ):
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
        widget.field_name = unique_field_name(document, f"__radio_{group_name}_{index}")
        widget.field_label = option
        widget.field_value = False
        widget.rect = position
        widget.text_font = "ZaDb"
        widget.text_fontsize = 0
        _style_box_widget(widget)
        annotation = page.add_widget(widget)
        child_xref = int(annotation.xref)
        _replace_button_on_state(document, child_xref, state)
        document.xref_set_key(
            child_xref, PDF_STUDIO_OPTION_KEY, fitz.get_pdf_str(option)
        )
        child_xrefs.append(child_xref)

    parent_xref = document.get_new_xref()
    kids = "[ " + " ".join(f"{xref} 0 R" for xref in child_xrefs) + " ]"
    flags = fitz.PDF_BTN_FIELD_IS_RADIO | fitz.PDF_BTN_FIELD_IS_NO_TOGGLE_TO_OFF
    parent = (
        f"<< /FT /Btn /Ff {flags} /T {fitz.get_pdf_str(group_name)} "
        f"/TU {fitz.get_pdf_str(label or group_name)} /Kids {kids} "
        f"/V /Off /DV /Off /{PDF_STUDIO_KIND_KEY} /{KIND_RADIO_GROUP} >>"
    )
    document.update_object(parent_xref, parent)

    for child_xref in child_xrefs:
        for key in ("FT", "Ff", "T", "TU", "V", "DV"):
            document.xref_set_key(child_xref, key, "null")
        document.xref_set_key(child_xref, "Parent", f"{parent_xref} 0 R")

    top_level = _top_level_field_refs(document)
    top_level = [xref for xref in top_level if xref not in child_xrefs]
    top_level.append(parent_xref)
    _set_top_level_field_refs(document, top_level)

    page = document.load_page(page_number)
    by_xref = {int(widget.xref): widget for widget in page.widgets() or []}
    return [by_xref[xref] for xref in child_xrefs]


def widget_custom_kind(document: fitz.Document, xref: int) -> str | None:
    value_type, value = document.xref_get_key(int(xref), PDF_STUDIO_KIND_KEY)
    if value_type == "name":
        return value.lstrip("/")
    if value_type == "string":
        return value
    parent = radio_parent_xref(document, int(xref))
    if parent is not None:
        value_type, value = document.xref_get_key(parent, PDF_STUDIO_KIND_KEY)
        if value_type == "name":
            return value.lstrip("/")
    return None


def radio_option_label(document: fitz.Document, xref: int) -> str | None:
    value_type, value = document.xref_get_key(int(xref), PDF_STUDIO_OPTION_KEY)
    return value if value_type == "string" else None


def radio_parent_xref(document: fitz.Document, child_xref: int) -> int | None:
    value_type, value = document.xref_get_key(int(child_xref), "Parent")
    if value_type == "xref":
        return int(value.split()[0])
    return None


def radio_group_member_refs(document: fitz.Document, child_xref: int) -> list[int]:
    parent = radio_parent_xref(document, child_xref)
    if parent is None:
        return [int(child_xref)]
    value_type, value = document.xref_get_key(parent, "Kids")
    if value_type != "array":
        return [int(child_xref)]
    return [int(match) for match in re.findall(r"(\d+)\s+0\s+R", value)]


def _find_widget_on_page(page: fitz.Page, xref: int) -> fitz.Widget | None:
    for widget in page.widgets() or []:
        if int(widget.xref) == int(xref):
            return widget
    return None


def find_widget(
    document: fitz.Document,
    page_number: int,
    xref: int,
) -> fitz.Widget | None:
    if not (0 <= page_number < document.page_count):
        return None
    page = document.load_page(page_number)
    return _find_widget_on_page(page, xref)


def move_or_resize_widget(
    document: fitz.Document,
    page_number: int,
    xref: int,
    rect: fitz.Rect,
) -> fitz.Widget:
    page = document.load_page(page_number)
    widget = _find_widget_on_page(page, xref)
    if widget is None:
        raise LookupError(f"Form field xref {xref} was not found on page {page_number + 1}.")

    if widget.field_type in (
        fitz.PDF_WIDGET_TYPE_CHECKBOX,
        fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
    ):
        minimum = (MIN_CHECKBOX_SIZE, MIN_CHECKBOX_SIZE)
    elif widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
        minimum = MIN_SIGNATURE_SIZE
    elif widget.field_type in (
        fitz.PDF_WIDGET_TYPE_COMBOBOX,
        fitz.PDF_WIDGET_TYPE_LISTBOX,
    ):
        minimum = MIN_CHOICE_SIZE
    else:
        minimum = MIN_TEXT_SIZE
    widget.rect = normalise_rect(
        rect,
        page.rect,
        min_width=minimum[0],
        min_height=minimum[1],
    )
    widget.update()
    return widget


def _remove_top_level_field(document: fitz.Document, xref: int) -> None:
    refs = _top_level_field_refs(document)
    if xref not in refs:
        return
    _set_top_level_field_refs(document, [item for item in refs if item != xref])


def delete_widget(document: fitz.Document, page_number: int, xref: int) -> bool:
    if not (0 <= page_number < document.page_count):
        return False
    page = document.load_page(page_number)
    widget = _find_widget_on_page(page, xref)
    if widget is None:
        return False

    parent = radio_parent_xref(document, xref)
    if widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON and parent is not None:
        member_refs = set(radio_group_member_refs(document, xref))
        for target_page_number in range(document.page_count):
            target_page = document.load_page(target_page_number)
            for member in list(target_page.widgets() or []):
                if int(member.xref) in member_refs:
                    target_page.delete_widget(member)
        _remove_top_level_field(document, parent)
        return True

    page.delete_widget(widget)
    return True


def _normalise_choices(choices: Sequence[str]) -> list[str]:
    values: list[str] = []
    for choice in choices:
        text = str(choice).strip()
        if text not in values:
            values.append(text)
    if len(values) < 2:
        raise ValueError("Dropdown fields require at least two distinct choices.")
    return values


def update_widget_properties(
    document: fitz.Document,
    page_number: int,
    xref: int,
    *,
    name: str,
    label: str,
    required: bool,
    read_only: bool,
    multiline: bool | None = None,
    choices: Sequence[str] | None = None,
    editable: bool | None = None,
) -> fitz.Widget:
    if not (0 <= page_number < document.page_count):
        raise LookupError(f"Page {page_number + 1} does not exist.")

    page = document.load_page(page_number)
    widget = _find_widget_on_page(page, xref)
    if widget is None:
        raise LookupError(
            f"Form field xref {xref} was not found on page {page_number + 1}."
        )
    original_name = str(widget.field_name or "")

    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Field name cannot be empty.")
    if clean_name != original_name and clean_name in existing_field_names(document):
        raise ValueError(f'A field named "{clean_name}" already exists.')

    parent_xref = radio_parent_xref(document, xref)
    if widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON and parent_xref is not None:
        flags_type, flags_value = document.xref_get_key(parent_xref, "Ff")
        flags = int(flags_value) if flags_type == "int" else fitz.PDF_BTN_FIELD_IS_RADIO
        flags &= ~(fitz.PDF_FIELD_IS_REQUIRED | fitz.PDF_FIELD_IS_READ_ONLY)
        if required:
            flags |= fitz.PDF_FIELD_IS_REQUIRED
        if read_only:
            flags |= fitz.PDF_FIELD_IS_READ_ONLY
        document.xref_set_key(parent_xref, "T", fitz.get_pdf_str(clean_name))
        document.xref_set_key(
            parent_xref, "TU", fitz.get_pdf_str(label.strip() or clean_name)
        )
        document.xref_set_key(parent_xref, "Ff", str(flags))
        page = document.load_page(page_number)
        updated = _find_widget_on_page(page, xref)
        if updated is None:
            raise LookupError("The radio group could not be reloaded.")
        return updated

    page = document.load_page(page_number)
    widget = _find_widget_on_page(page, xref)
    if widget is None:
        raise LookupError(
            f"Form field xref {xref} was not found on page {page_number + 1}."
        )

    flags = int(getattr(widget, "field_flags", 0) or 0)
    flags &= ~(fitz.PDF_FIELD_IS_REQUIRED | fitz.PDF_FIELD_IS_READ_ONLY)
    if required:
        flags |= fitz.PDF_FIELD_IS_REQUIRED
    if read_only:
        flags |= fitz.PDF_FIELD_IS_READ_ONLY

    if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT and multiline is not None:
        flags &= ~fitz.PDF_TX_FIELD_IS_MULTILINE
        if multiline and widget_custom_kind(document, xref) != KIND_DATE:
            flags |= fitz.PDF_TX_FIELD_IS_MULTILINE

    if widget.field_type == fitz.PDF_WIDGET_TYPE_COMBOBOX:
        flags |= fitz.PDF_CH_FIELD_IS_COMBO
        if editable is not None:
            flags &= ~fitz.PDF_CH_FIELD_IS_EDIT
            if editable:
                flags |= fitz.PDF_CH_FIELD_IS_EDIT
        if choices is not None:
            values = _normalise_choices(choices)
            widget.choice_values = values
            if str(widget.field_value or "") not in values:
                widget.field_value = values[0]

    widget.field_name = clean_name
    widget.field_label = label.strip() or clean_name
    widget.field_flags = flags
    widget.update()
    return widget
