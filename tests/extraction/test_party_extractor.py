from openpyxl import Workbook

from bedding_order_parser.diagnostics.models import AMBIGUOUS, EXTRACTED
from bedding_order_parser.excel.table_parser import parse_table
from bedding_order_parser.extraction.party_extractor import extract_parties


def _extract(rows: list[list[object]]):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "PI"
    for row in rows:
        worksheet.append(row)
    worksheet.append(["No.", "Item", "Size", "Specification", "QTY"])
    worksheet.append(["1", "Duvet Cover", "200*240cm", "100% cotton", "12"])
    return extract_parties(parse_table(worksheet))


def test_extracts_side_by_side_buyer_and_seller_regions() -> None:
    parties = _extract(
        [
            ["BUYER:", "", "", "SELLER:"],
            ["Bridgeway Company Limited", "", "", "Canasin International Textile (Jiangsu) Co., Ltd."],
            ["Contact Person: Buyer Alice", "", "", "Contact Person: Sophia Zhao"],
        ]
    )

    assert parties.customer.value == "Bridgeway Company Limited"
    assert parties.customer.status == EXTRACTED
    assert parties.salesperson.value == "Sophia Zhao"
    assert parties.salesperson.status == EXTRACTED
    assert parties.buyer_contact.value == "Buyer Alice"
    assert parties.customer.source.cells == ("A1", "A2")
    assert parties.salesperson.source.cells == ("D3",)


def test_extracts_vertically_stacked_buyer_and_seller_regions() -> None:
    parties = _extract(
        [
            ["Invoice To: Annupuri Garden 2"],
            ["Contact Person: Ms. Zhang"],
            ["From: Canasin International Textile (Jiangsu) Co., Ltd."],
            ["Contact Person: Layla Chen"],
        ]
    )

    assert parties.customer.value == "Annupuri Garden 2"
    assert parties.salesperson.value == "Layla Chen"
    assert parties.buyer_contact.value == "Ms. Zhang"


def test_buyer_label_supports_inline_and_adjacent_values() -> None:
    inline = _extract([["Buyer: HAI HA HANDICRAFT CO., LTD"]])
    adjacent = _extract([["Bill To:", "Welllife Company Limited"]])

    assert inline.customer.value == "HAI HA HANDICRAFT CO., LTD"
    assert adjacent.customer.value == "Welllife Company Limited"


def test_buyer_company_cleanup_preserves_suffix_and_branch() -> None:
    parties = _extract(
        [
            [
                "Messers: Asset World Wex Co., Ltd. (Branch 00004)\n"
                "Address: 101/45 Moo 20\nPhone: 12345"
            ],
            ["Seller: Canasin", "", "", "Contact Person: Sophia Zhao"],
        ]
    )

    assert parties.customer.value == "Asset World Wex Co., Ltd. (Branch 00004)"
    assert "Address" not in parties.customer.value
    assert "Phone" not in parties.customer.value


def test_to_buyer_cleanup_uses_legal_suffix_before_unlabeled_address() -> None:
    parties = _extract(
        [
            ["Canasin International Textile (Jiangsu) Co., Ltd."],
            ["Vincy Lu TEL: +86 123 Mobile: +86 456 E-mail: vincy@canasin.com"],
            [
                "To buyer: Amin Construction Pvt Ltd 2nd Floor, M. World Dream Building "
                "Company Reg. No: C-20/1989 Tel: +960-3324369"
            ],
        ]
    )

    assert parties.customer.value == "Amin Construction Pvt Ltd"
    assert parties.salesperson.value == "Vincy Lu"


def test_use_hotel_and_buyer_contact_do_not_override_buyer() -> None:
    parties = _extract(
        [
            ["BUYER:", "", "", "SELLER:"],
            ["Bridgeway Company Limited", "", "", "Canasin"],
            ["Contact Person: Buyer Alice", "", "", "Contact Person: Sophia Zhao"],
            ["Use Hotel: EASE HOTEL MANDALAY"],
        ]
    )

    assert parties.customer.value == "Bridgeway Company Limited"
    assert parties.salesperson.value == "Sophia Zhao"
    assert parties.buyer_contact.value == "Buyer Alice"


def test_explicit_seller_contact_precedes_signature_name() -> None:
    parties = _extract(
        [
            ["Messers: Hann Philippines, Inc.", "", "", "From: Canasin"],
            ["Contact Person: Mr. Daniel Yumul", "", "", "Contact Person: Michael"],
            ["Authorized Signature: Michael Cho"],
        ]
    )

    assert parties.customer.value == "Hann Philippines, Inc."
    assert parties.salesperson.value == "Michael"


def test_conflicting_buyers_are_ambiguous() -> None:
    parties = _extract(
        [
            ["Buyer: First Company Limited"],
            ["Buyer: Second Company Limited"],
            ["Seller: Canasin"],
            ["Contact Person: Sophia Zhao"],
        ]
    )

    assert parties.customer.value == ""
    assert parties.customer.status == AMBIGUOUS


def test_conflicting_seller_contacts_are_ambiguous() -> None:
    parties = _extract(
        [
            ["Buyer: Customer Company Limited", "", "", "Seller: Canasin"],
            ["", "", "", "Contact Person: Sophia Zhao"],
            ["", "", "", "Contact Person: Layla Chen"],
        ]
    )

    assert parties.salesperson.value == ""
    assert parties.salesperson.status == AMBIGUOUS
