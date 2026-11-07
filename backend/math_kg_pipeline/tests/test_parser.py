from src.parser import parse_document

def test_parse_question_and_solution():
    pages = [{
        "page": 1,
        "text": "Câu 1. Giải phương trình x + 1 = 2\\nLời giải: x = 1"
    }]
    result = parse_document(pages)
    assert len(result) == 1
    assert "x + 1 = 2" in result[0]["question_text"]
    assert "x = 1" in result[0]["solution_text"]


def test_solution_continuing_on_next_page_stays_with_question():
    pages = [
        {"page": 1, "text": "Câu 5. Tính x.\nLời giải: x ="},
        {"page": 2, "text": "2\nVậy x = 2"},
    ]

    result = parse_document(pages)

    assert len(result) == 1
    assert result[0]["pages"] == [1, 2]
    assert result[0]["question_text"] == "Tính x."
    assert result[0]["solution_text"] == "x =\n2\nVậy x = 2"
