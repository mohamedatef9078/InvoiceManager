import html
import json
import xml.etree.ElementTree as ET
from datetime import datetime


class InvoiceXMLReadError(Exception):
    """خطأ أثناء قراءة ملف الفاتورة."""

    pass


# ---------------------------------------------------------
# دوال تنظيف وقراءة البيانات
# ---------------------------------------------------------

def clean_tag(tag):
    """حذف namespace من اسم عنصر XML."""

    return str(tag).split("}")[-1]


def normalize_key(key):
    """توحيد شكل أسماء المفاتيح للمقارنة."""

    return (
        clean_tag(key)
        .replace("_", "")
        .replace("-", "")
        .lower()
    )


def decode_json_value(value):
    """
    تحويل أي نص JSON داخلي إلى قاموس أو قائمة.
    """

    if not isinstance(value, str):
        return value

    text = html.unescape(value).strip()

    if not text:
        return value

    if not (
        (text.startswith("{") and text.endswith("}"))
        or
        (text.startswith("[") and text.endswith("]"))
    ):
        return value

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        return value


def prepare_data(data):
    """
    المرور على البيانات وتحويل نصوص JSON الداخلية
    إلى قواميس وقوائم حقيقية.
    """

    data = decode_json_value(data)

    if isinstance(data, dict):
        return {
            clean_tag(key): prepare_data(value)
            for key, value in data.items()
        }

    if isinstance(data, list):
        return [
            prepare_data(item)
            for item in data
        ]

    return data


def find_value(data, *possible_keys, default=""):
    """
    البحث عن أول قيمة مطابقة داخل جميع مستويات البيانات.
    """

    wanted_keys = {
        normalize_key(key)
        for key in possible_keys
    }

    data = decode_json_value(data)

    if isinstance(data, dict):
        for key, value in data.items():
            if (
                normalize_key(key) in wanted_keys
                and value not in (None, "", [], {})
            ):
                return decode_json_value(value)

        for value in data.values():
            result = find_value(
                value,
                *possible_keys,
                default=None,
            )

            if result not in (None, "", [], {}):
                return result

    elif isinstance(data, list):
        for item in data:
            result = find_value(
                item,
                *possible_keys,
                default=None,
            )

            if result not in (None, "", [], {}):
                return result

    return default


def find_all_values(data, *possible_keys):
    """
    جمع كل القيم التي تحمل أسماء معينة.
    """

    results = []

    wanted_keys = {
        normalize_key(key)
        for key in possible_keys
    }

    data = decode_json_value(data)

    if isinstance(data, dict):
        for key, value in data.items():
            decoded_value = decode_json_value(value)

            if normalize_key(key) in wanted_keys:
                results.append(decoded_value)

            results.extend(
                find_all_values(
                    decoded_value,
                    *possible_keys,
                )
            )

    elif isinstance(data, list):
        for item in data:
            results.extend(
                find_all_values(
                    item,
                    *possible_keys,
                )
            )

    return results


def xml_element_to_dict(element):
    """
    تحويل XML إلى قاموس Python.
    """

    children = list(element)

    if not children:
        return decode_json_value(
            (element.text or "").strip()
        )

    result = {}

    for child in children:
        child_name = clean_tag(child.tag)
        child_value = xml_element_to_dict(child)

        if child_name in result:
            if not isinstance(result[child_name], list):
                result[child_name] = [
                    result[child_name]
                ]

            result[child_name].append(child_value)

        else:
            result[child_name] = child_value

    return result


# ---------------------------------------------------------
# تحويل الأرقام والتاريخ والعنوان
# ---------------------------------------------------------

def to_number(value):
    """
    تحويل القيمة إلى رقم عشري بأمان.
    """

    value = decode_json_value(value)

    if value in (None, "", [], {}):
        return 0.0

    if isinstance(value, list):
        total = 0.0

        for item in value:
            total += to_number(item)

        return total

    if isinstance(value, dict):
        amount = find_value(
            value,
            "amount",
            "taxAmount",
            "value",
            "totalAmount",
            default=None,
        )

        if amount is None:
            return 0.0

        return to_number(amount)

    try:
        number_text = (
            str(value)
            .replace(",", "")
            .replace("٬", "")
            .replace(" ", "")
            .strip()
        )

        return float(number_text)

    except (ValueError, TypeError):
        return 0.0


def format_invoice_date(date_value):
    """
    تحويل التاريخ إلى يوم/شهر/سنة.
    """

    if not date_value:
        return ""

    date_text = str(date_value).strip()

    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]

    for date_format in formats:
        try:
            parsed_date = datetime.strptime(
                date_text,
                date_format,
            )

            return parsed_date.strftime("%d/%m/%Y")

        except ValueError:
            continue

    return date_text


def format_address(address):
    """
    تحويل عنوان العميل أو البائع إلى نص.
    """

    address = decode_json_value(address)

    if not address:
        return ""

    if isinstance(address, str):
        return address.strip()

    if isinstance(address, list):
        parts = [
            format_address(item)
            for item in address
        ]

        return " - ".join(
            part
            for part in parts
            if part
        )

    if isinstance(address, dict):
        parts = [
            find_value(
                address,
                "buildingNumber",
                "building",
                default="",
            ),
            find_value(
                address,
                "street",
                "streetName",
                default="",
            ),
            find_value(
                address,
                "regionCity",
                "city",
                default="",
            ),
            find_value(
                address,
                "governate",
                "governorate",
                "state",
                default="",
            ),
            find_value(
                address,
                "postalCode",
                default="",
            ),
            find_value(
                address,
                "country",
                "countryName",
                default="",
            ),
        ]

        return " - ".join(
            str(part).strip()
            for part in parts
            if part not in (None, "", [], {})
        )

    return str(address).strip()


# ---------------------------------------------------------
# قراءة الضرائب
# ---------------------------------------------------------

def collect_tax_items(data):
    """
    جمع عناصر الضرائب من أي مكان داخل الفاتورة.
    """

    tax_items = []

    data = decode_json_value(data)

    if isinstance(data, dict):
        tax_type = find_value_direct(
            data,
            "taxType",
            "taxCode",
            default="",
        )

        tax_amount = find_value_direct(
            data,
            "amount",
            "taxAmount",
            default=None,
        )

        if tax_type and tax_amount is not None:
            tax_items.append(data)

        for value in data.values():
            tax_items.extend(
                collect_tax_items(value)
            )

    elif isinstance(data, list):
        for item in data:
            tax_items.extend(
                collect_tax_items(item)
            )

    return tax_items


def find_value_direct(data, *possible_keys, default=""):
    """
    البحث داخل المستوى الحالي فقط.
    """

    if not isinstance(data, dict):
        return default

    wanted_keys = {
        normalize_key(key)
        for key in possible_keys
    }

    for key, value in data.items():
        if (
            normalize_key(key) in wanted_keys
            and value not in (None, "")
        ):
            return decode_json_value(value)

    return default


def get_tax_amount(document_data, wanted_code):
    """
    استخراج قيمة نوع الضريبة.

    T1 = ضريبة القيمة المضافة.
    T4 = الخصم تحت حساب الضريبة.
    """

    wanted_code = str(wanted_code).upper().strip()

    # نحاول أولًا قراءة إجمالي ضرائب المستند
    tax_totals = find_value(
        document_data,
        "taxTotals",
        "taxTotal",
        default=[],
    )

    tax_items = collect_tax_items(tax_totals)

    total = 0.0
    found = False

    for tax_item in tax_items:
        tax_code = str(
            find_value_direct(
                tax_item,
                "taxType",
                "taxCode",
                default="",
            )
        ).upper().strip()

        if tax_code == wanted_code:
            amount = to_number(
                find_value_direct(
                    tax_item,
                    "amount",
                    "taxAmount",
                    default=0,
                )
            )

            total += amount
            found = True

    if found:
        return total

    # محاولة بديلة من أسماء الحقول المباشرة
    if wanted_code == "T1":
        return to_number(
            find_value(
                document_data,
                "vat",
                "vatAmount",
                "valueAddedTax",
                "valueAddedTaxAmount",
                default=0,
            )
        )

    if wanted_code == "T4":
        return to_number(
            find_value(
                document_data,
                "withholdingTax",
                "withholdingTaxAmount",
                "discountTax",
                default=0,
            )
        )

    return 0.0


# ---------------------------------------------------------
# استخراج بيانات document
# ---------------------------------------------------------

def find_document_element(root):
    """
    البحث عن عنصر document داخل XML.
    """

    for element in root.iter():
        if clean_tag(element.tag).lower() == "document":
            return element

    return None


def get_document_data(document_element):
    """
    استخراج محتوى عنصر document.
    """

    direct_text = (
        document_element.text or ""
    ).strip()

    if direct_text:
        decoded_text = html.unescape(direct_text).strip()

        try:
            result = json.loads(decoded_text)

            return prepare_data(result)

        except json.JSONDecodeError:
            pass

    if list(document_element):
        result = xml_element_to_dict(
            document_element
        )

        return prepare_data(result)

    all_text = "".join(
        document_element.itertext()
    ).strip()

    if all_text:
        decoded_text = html.unescape(all_text).strip()

        try:
            result = json.loads(decoded_text)

            return prepare_data(result)

        except json.JSONDecodeError:
            pass

    raise InvoiceXMLReadError(
        "تعذر استخراج بيانات الفاتورة من عنصر document."
    )


def unwrap_document(document_data):
    """
    فك أي تغليف زائد حول بيانات الفاتورة.
    """

    document_data = prepare_data(document_data)

    if isinstance(document_data, list):
        for item in document_data:
            if isinstance(item, dict):
                return unwrap_document(item)

        return {}

    if not isinstance(document_data, dict):
        return {}

    for key in (
        "documents",
        "document",
        "invoice",
        "invoices",
    ):
        nested = find_value_direct(
            document_data,
            key,
            default=None,
        )

        if isinstance(nested, list) and nested:
            if isinstance(nested[0], dict):
                return unwrap_document(nested[0])

        if isinstance(nested, dict):
            return unwrap_document(nested)

    return document_data


# ---------------------------------------------------------
# قراءة الفاتورة
# ---------------------------------------------------------

def read_invoice_xml(xml_file):
    """
    قراءة ملف الفاتورة وإرجاع البيانات المطلوبة.
    """

    try:
        xml_file.seek(0)

    except (AttributeError, OSError):
        pass

    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

    except ET.ParseError as error:
        raise InvoiceXMLReadError(
            "ملف XML غير صالح أو تالف."
        ) from error

    except Exception as error:
        raise InvoiceXMLReadError(
            "تعذر فتح ملف XML وقراءته."
        ) from error

    document_element = find_document_element(root)

    if document_element is None:
        raise InvoiceXMLReadError(
            "لم يتم العثور على عنصر document داخل الملف."
        )

    document_data = unwrap_document(
        get_document_data(document_element)
    )

    if not document_data:
        raise InvoiceXMLReadError(
            "تعذر فهم بيانات الفاتورة."
        )

    issuer = find_value(
        document_data,
        "issuer",
        "seller",
        default={},
    )

    receiver = find_value(
        document_data,
        "receiver",
        "buyer",
        default={},
    )

    if isinstance(issuer, list):
        issuer = issuer[0] if issuer else {}

    if isinstance(receiver, list):
        receiver = receiver[0] if receiver else {}

    if not isinstance(issuer, dict):
        issuer = {}

    if not isinstance(receiver, dict):
        receiver = {}

    # رقم الفاتورة: الرقم الداخلي أولًا
    invoice_number = find_value_direct(
        document_data,
        "internalID",
        "internalId",
        "internal_id",
        default="",
    )

    if not invoice_number:
        invoice_number = find_value(
            document_data,
            "internalID",
            "internalId",
            "invoiceNumber",
            "invoiceNo",
            "documentNumber",
            default="",
        )

    if not invoice_number:
        invoice_number = find_value(
            document_data,
            "uuid",
            default="",
        )

    # القيم الأساسية
    before_tax = to_number(
        find_value(
            document_data,
            "totalSalesAmount",
            "salesTotal",
            "beforeTax",
            default=0,
        )
    )

    net_amount = to_number(
        find_value(
            document_data,
            "netAmount",
            "netTotal",
            default=0,
        )
    )

    total_discount = to_number(
        find_value(
            document_data,
            "totalDiscountAmount",
            "extraDiscountAmount",
            "totalItemsDiscountAmount",
            "discountAmount",
            default=0,
        )
    )

    vat = get_tax_amount(
        document_data,
        "T1",
    )

    withholding_tax = get_tax_amount(
        document_data,
        "T4",
    )

    after_tax = to_number(
        find_value(
            document_data,
            "totalAmount",
            "grandTotal",
            "invoiceTotal",
            "afterTax",
            default=0,
        )
    )

    # حلول احتياطية لو بعض القيم ناقصة
    if before_tax == 0 and net_amount > 0:
        before_tax = net_amount + total_discount

    if before_tax == 0 and after_tax > 0:
        before_tax = (
            after_tax
            - vat
            + withholding_tax
            + total_discount
        )

    if after_tax == 0:
        calculation_base = (
            net_amount
            if net_amount > 0
            else before_tax - total_discount
        )

        after_tax = (
            calculation_base
            + vat
            - withholding_tax
        )

    invoice_date = format_invoice_date(
        find_value(
            document_data,
            "dateTimeIssued",
            "invoiceDate",
            "issueDate",
            "date",
            default="",
        )
    )

    buyer_address = find_value(
        receiver,
        "address",
        default={},
    )

    seller_address = find_value(
        issuer,
        "address",
        default={},
    )

    buyer_name = str(
        find_value(
            receiver,
            "name",
            default=find_value(
                document_data,
                "buyerName",
                default="",
            ),
        )
    ).strip()

    buyer_registration = str(
        find_value(
            receiver,
            "id",
            "registrationNumber",
            "registration",
            default=find_value(
                document_data,
                "buyerRegistration",
                default="",
            ),
        )
    ).strip()

    seller_name = str(
        find_value(
            issuer,
            "name",
            default=find_value(
                document_data,
                "sellerName",
                default="",
            ),
        )
    ).strip()

    seller_registration = str(
        find_value(
            issuer,
            "id",
            "registrationNumber",
            "registration",
            default=find_value(
                document_data,
                "sellerRegistration",
                default="",
            ),
        )
    ).strip()

    return {
        "invoice_number": str(invoice_number).strip(),
        "invoice_date": invoice_date,

        "buyer_name": buyer_name,
        "buyer_registration": buyer_registration,
        "buyer_address": format_address(buyer_address),

        "seller_name": seller_name,
        "seller_registration": seller_registration,
        "seller_address": format_address(seller_address),

        "before_tax": round(before_tax, 2),
        "vat": round(vat, 2),
        "withholding_tax": round(withholding_tax, 2),
        "after_tax": round(after_tax, 2),
    }