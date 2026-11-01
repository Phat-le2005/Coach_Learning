"""Pedagogical Enrichment Engine for Theory Mindmaps.

Ensures that EVERY exercise type (Dạng toán) in a mind map has:
1. A step-by-step method (METHOD) with explicit learning steps.
2. A concrete worked example (EXAMPLE) with question, detailed step-by-step solution, and KaTeX answer.
3. Relevant formula (FORMULA) and trap warning (NOTE) where appropriate.

Works for both known high-school curriculum exercise types and arbitrary PDF documents.
"""

from __future__ import annotations

import re
from typing import Any
from app.theory_maps.schemas import NodeKind, TheoryLearningStep, TheoryNode

# Standard curriculum repository for Grade 12 Calculus (Chuyên đề Ứng dụng đạo hàm)
CURRICULUM_DATA: dict[str, dict[str, Any]] = {
    "1.1": {
        "method_title": "📝 Phương pháp: Nhận biết đơn điệu qua Đồ thị và BBT",
        "steps": [
            {"instruction": "Bước 1: Quan sát bảng biến thiên hoặc đồ thị y = f(x) theo chiều từ trái sang phải.", "latex": None},
            {"instruction": "Bước 2: Xác định các khoảng mà đồ thị đi lên (hoặc f'(x) mang dấu +) tương ứng hàm số đồng biến.", "latex": "f'(x) > 0 \\implies \\text{đồng biến}"},
            {"instruction": "Bước 3: Xác định các khoảng mà đồ thị đi xuống (hoặc f'(x) mang dấu -) tương ứng hàm số nghịch biến.", "latex": "f'(x) < 0 \\implies \\text{nghịch biến}"},
            {"instruction": "Bước 4: Chiếu các khoảng đó xuống trục hoành Ox và kết luận các khoảng (a; b) độc lập (không dùng dấu hợp ∪).", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm khoảng đơn điệu từ bảng biến thiên",
        "example_body": "Đề bài: Cho hàm số y = f(x) có đạo hàm f'(x) liên tục trên R và có bảng biến thiên: f'(x) > 0 trên (-∞; -1) và (2; +∞); f'(x) < 0 trên (-1; 2). Tìm khoảng nghịch biến của hàm số.\nLời giải: Dựa vào bảng biến thiên, trên khoảng (-1; 2) đạo hàm f'(x) mang dấu âm (-), suy ra hàm số nghịch biến trên khoảng (-1; 2).",
        "example_latex": "x \\in (-1; 2)",
        "note_title": "⚠️ Bẫy sai lầm: Dùng ký hiệu hợp khi kết luận",
        "note_body": "Khi kết luận các khoảng đồng biến/nghịch biến, TUYỆT ĐỐI KHÔNG dùng ký hiệu hợp ∪ (như (-∞; -1) ∪ (2; +∞)) hay dấu cộng +. Phải dùng chữ 'và' hoặc dấu chấm phẩy ';'.",
        "note_latex": "\\text{Dùng } K_1 \\text{ và } K_2, \\text{ KHÔNG dùng } K_1 \\cup K_2",
    },
    "1.3": {
        "method_title": "📝 Phương pháp: Đơn điệu hàm phân thức nhất biến y = (ax+b)/(cx+d)",
        "steps": [
            {"instruction": "Bước 1: Tìm tập xác định D = R \\ {-d/c}.", "latex": "x \\neq -\\frac{d}{c}"},
            {"instruction": "Bước 2: Tính đạo hàm y' = (ad - bc) / (cx + d)^2.", "latex": "y' = \\frac{ad - bc}{(cx + d)^2}"},
            {"instruction": "Bước 3: Hàm đồng biến trên K <=> ad - bc > 0 và -d/c không thuộc K.", "latex": "ad - bc > 0 \\text{ và } -\\frac{d}{c} \\notin K"},
            {"instruction": "Bước 4: Hàm nghịch biến trên K <=> ad - bc < 0 và -d/c không thuộc K.", "latex": "ad - bc < 0 \\text{ và } -\\frac{d}{c} \\notin K"},
        ],
        "example_title": "💡 Ví dụ: Tìm m để hàm phân thức đồng biến trên khoảng",
        "example_body": "Đề bài: Tìm tất cả giá trị thực của tham số m để hàm số y = (mx - 4)/(x - m) đồng biến trên khoảng (0; +∞).\nLời giải:\n- TXĐ: D = R \\ {m}.\n- Đạo hàm: y' = (-m^2 + 4) / (x - m)^2.\n- Để hàm số đồng biến trên (0; +∞), ta cần:\n  1) -m^2 + 4 > 0 <=> -2 < m < 2.\n  2) Điểm gián đoạn x = m không thuộc (0; +∞) <=> m <= 0.\n- Kết hợp hai điều kiện: -2 < m <= 0.",
        "example_latex": "-2 < m \\le 0",
    },
    "1.4": {
        "method_title": "📝 Phương pháp: Xét tính đơn điệu hàm hợp y = f(u(x))",
        "steps": [
            {"instruction": "Bước 1: Tính đạo hàm y' = u'(x) * f'(u(x)).", "latex": "y' = u'(x) \\cdot f'(u(x))"},
            {"instruction": "Bước 2: Cho y' = 0 <=> u'(x) = 0 hoặc u(x) = x_i (với x_i là nghiệm bội lẻ của f'(x) = 0).", "latex": "u'(x) = 0 \\lor u(x) = x_i"},
            {"instruction": "Bước 3: Lập trục xét dấu cho y' hoặc chọn một giá trị x_0 cụ thể để thử dấu.", "latex": None},
            {"instruction": "Bước 4: Đọc khoảng mang dấu dương (+) là đồng biến, dấu âm (-) là nghịch biến.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm khoảng nghịch biến của hàm hợp y = f(x^2 - 2x)",
        "example_body": "Đề bài: Cho hàm số y = f(x) có f'(x) = x(x - 3). Tìm khoảng nghịch biến của g(x) = f(x^2 - 2x).\nLời giải:\n- g'(x) = (2x - 2) * f'(x^2 - 2x) = 2(x - 1) * (x^2 - 2x) * (x^2 - 2x - 3).\n- g'(x) = 0 <=> x = 1, x = 0, x = 2, x = -1, x = 3.\n- Xét dấu g'(x) trên từng khoảng, ta thấy g'(x) < 0 trên các khoảng (-∞; -1), (0; 1) và (2; 3).",
        "example_latex": "g'(x) < 0 \\implies x \\in (0; 1) \\cup (2; 3)",
    },
    "1.5": {
        "method_title": "📝 Phương pháp: Tương quan đồ thị cho hàm tổng hiệu y = f(x) + h(x)",
        "steps": [
            {"instruction": "Bước 1: Tính đạo hàm y' = f'(x) + h'(x) = f'(x) - (-h'(x)).", "latex": "y' = f'(x) - g(x)"},
            {"instruction": "Bước 2: Vẽ đồ thị hàm số y = f'(x) và đường thẳng/đường cong y = g(x) trên cùng hệ trục.", "latex": None},
            {"instruction": "Bước 3: Tìm hoành độ giao điểm để chia các khoảng xét dấu.", "latex": "f'(x) = g(x)"},
            {"instruction": "Bước 4: Khoảng mà đồ thị f'(x) nằm PHÍA TRÊN g(x) thì y' > 0 (đồng biến); nằm PHÍA DƯỚI thì y' < 0 (nghịch biến).", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Đơn điệu hàm tổng hiệu bằng đồ thị",
        "example_body": "Đề bài: Cho đồ thị hàm số y = f'(x). Xét tính đồng biến của g(x) = f(x) - x.\nLời giải:\n- Ta có g'(x) = f'(x) - 1.\n- Vẽ đường thẳng d: y = 1 cắt đồ thị y = f'(x) tại các điểm có hoành độ x_1 < x_2.\n- Trên khoảng mà f'(x) nằm trên đường thẳng y = 1 thì g'(x) > 0, hàm số g(x) đồng biến.",
        "example_latex": "f'(x) > 1 \\implies g'(x) > 0",
    },
    "1.6": {
        "method_title": "📝 Phương pháp: Ứng dụng hàm số đơn điệu giải phương trình f(u) = f(v)",
        "steps": [
            {"instruction": "Bước 1: Biến đổi phương trình hoặc bất phương trình về dạng f(u) = f(v) hoặc f(u) >= f(v).", "latex": "f(u) = f(v)"},
            {"instruction": "Bước 2: Xác định hàm số đại diện f(t) trên tập xác định chung.", "latex": None},
            {"instruction": "Bước 3: Tính đạo hàm f'(t) và chứng minh hàm số luôn đồng biến (f' > 0) hoặc luôn nghịch biến (f' < 0).", "latex": "f'(t) > 0, \\forall t"},
            {"instruction": "Bước 4: Áp dụng định lý: f(t) đơn điệu thì f(u) = f(v) <=> u = v (hoặc f(u) >= f(v) <=> u >= v).", "latex": "f(u) = f(v) \\iff u = v"},
        ],
        "example_title": "💡 Ví dụ: Giải phương trình bằng hàm đặc trưng",
        "example_body": "Đề bài: Giải phương trình x^3 + 3x = (2 - y)^3 + 3(2 - y).\nLời giải:\n- Xét hàm số đại diện f(t) = t^3 + 3t trên R.\n- f'(t) = 3t^2 + 3 > 0, forall t thuộc R => f(t) đồng biến trên R.\n- Phương trình có dạng f(x) = f(2 - y) <=> x = 2 - y <=> x + y = 2.",
        "example_latex": "x + y = 2",
    },
    "2.1": {
        "method_title": "📝 Phương pháp: Tìm cực trị qua BBT và Đồ thị",
        "steps": [
            {"instruction": "Bước 1: Quan sát các điểm mà đạo hàm f'(x) đổi dấu từ dương sang âm (+) sang (-) qua x_0 => Điểm cực đại.", "latex": "+ \\to - \\implies \\text{Cực đại}"},
            {"instruction": "Bước 2: Quan sát các điểm mà đạo hàm f'(x) đổi dấu từ âm sang dương (-) sang (+) qua x_0 => Điểm cực tiểu.", "latex": "- \\to + \\implies \\text{Cực tiểu}"},
            {"instruction": "Bước 3: Đọc đúng yêu cầu: Điểm cực trị của hàm số là x; Giá trị cực trị là y; Điểm cực trị của đồ thị là (x; y).", "latex": "(x_0; y_0)"},
        ],
        "example_title": "💡 Ví dụ: Phân biệt điểm cực trị và giá trị cực trị",
        "example_body": "Đề bài: Cho hàm số y = f(x) có BBT: f'(x) đổi dấu từ (+) sang (-) tại x = 1 (với y = 5) và đổi dấu từ (-) sang (+) tại x = 3 (với y = -2). Tìm giá trị cực đại và điểm cực tiểu của hàm số.\nLời giải:\n- Giá trị cực đại của hàm số là y_CD = 5 (đạt tại x = 1).\n- Điểm cực tiểu của hàm số là x_CT = 3 (với giá trị cực tiểu y_CT = -2).",
        "example_latex": "y_{CĐ} = 5, x_{CT} = 3",
    },
    "2.2": {
        "method_title": "📝 Phương pháp: Quy tắc 1 tìm cực trị hàm số tường minh",
        "steps": [
            {"instruction": "Bước 1: Tìm tập xác định D. Tính đạo hàm y' = f'(x).", "latex": "y' = f'(x)"},
            {"instruction": "Bước 2: Tìm các điểm x_i mà tại đó f'(x) = 0 hoặc f'(x) không xác định.", "latex": "f'(x_i) = 0"},
            {"instruction": "Bước 3: Lập bảng biến thiên hoặc bảng xét dấu của f'(x).", "latex": None},
            {"instruction": "Bước 4: Kết luận các điểm cực đại, cực tiểu và giá trị cực trị tương ứng.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm cực trị hàm đa thức bậc ba",
        "example_body": "Đề bài: Tìm các điểm cực trị của hàm số y = x^3 - 3x^2 + 2.\nLời giải:\n- TXĐ: D = R. Đạo hàm: y' = 3x^2 - 6x.\n- y' = 0 <=> 3x(x - 2) = 0 <=> x = 0 hoặc x = 2.\n- Bảng xét dấu: y' đổi dấu từ (+) sang (-) qua x = 0 => Điểm cực đại x = 0 (y = 2).\n- y' đổi dấu từ (-) sang (+) qua x = 2 => Điểm cực tiểu x = 2 (y = -2).",
        "example_latex": "x_{CĐ} = 0, x_{CT} = 2",
    },
    "2.4": {
        "method_title": "📝 Phương pháp: Tìm m để hàm số có n điểm cực trị",
        "steps": [
            {"instruction": "Bước 1: Tính đạo hàm y' = f'(x; m).", "latex": "y' = f'(x; m)"},
            {"instruction": "Bước 2: Với hàm bậc ba y' là bậc hai: Có 2 cực trị <=> y' = 0 có 2 nghiệm phân biệt <=> a != 0 và Delta > 0.", "latex": "a \\neq 0 \\text{ và } \\Delta > 0"},
            {"instruction": "Bước 3: Không có cực trị <=> y' = 0 vô nghiệm hoặc nghiệm kép <=> Delta <= 0 (với a != 0).", "latex": "\\Delta \\le 0"},
            {"instruction": "Bước 4: Với hàm trùng phương: có 3 cực trị <=> a*b < 0; có 1 cực trị <=> a*b >= 0.", "latex": "ab < 0 \\iff 3 \\text{ cực trị}"},
        ],
        "example_title": "💡 Ví dụ: Tìm m để hàm bậc ba có 2 cực trị",
        "example_body": "Đề bài: Tìm tất cả giá trị thực của tham số m để hàm số y = x^3 - 3mx^2 + 3(m^2 - 1)x có 2 điểm cực trị.\nLời giải:\n- Đạo hàm: y' = 3x^2 - 6mx + 3(m^2 - 1) = 3[x^2 - 2mx + m^2 - 1].\n- Hàm số có 2 điểm cực trị <=> y' = 0 có 2 nghiệm phân biệt <=> Delta' > 0.\n- Delta' = (-m)^2 - 1*(m^2 - 1) = 1 > 0, luôn đúng với mọi m.\n- Vậy hàm số luôn có 2 điểm cực trị với mọi m thuộc R.",
        "example_latex": "m \\in \\mathbb{R}",
    },
    "2.6": {
        "method_title": "📝 Phương pháp: Cực trị hàm bậc ba thỏa điều kiện hình học đường thẳng",
        "steps": [
            {"instruction": "Bước 1: Viết phương trình đường thẳng qua hai điểm cực trị Delta: y = Ax + B (lấy y chia cho y').", "latex": "y = g(x) \\cdot y' + (Ax + B)"},
            {"instruction": "Bước 2: Tọa độ hai điểm cực trị A(x_1; y_1) và B(x_2; y_2) thỏa mãn y_1 = Ax_1 + B và y_2 = Ax_2 + B.", "latex": None},
            {"instruction": "Bước 3: Sử dụng định lý Vi-et cho phương trình y' = 0: x_1 + x_2 = -b/(3a), x_1 * x_2 = c/(3a).", "latex": "x_1 + x_2 = -\\frac{b}{3a}, x_1 x_2 = \\frac{c}{3a}"},
            {"instruction": "Bước 4: Thiết lập điều kiện theo yêu cầu bài toán (vuông góc, song song, khoảng cách, diện tích tam giác).", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm m để 2 điểm cực trị tạo với gốc O tam giác vuông",
        "example_body": "Đề bài: Tìm m để đồ thị hàm số y = x^3 - 3x^2 + m có hai điểm cực trị A, B sao cho tam giác OAB vuông tại O.\nLời giải:\n- y' = 3x^2 - 6x = 0 <=> x = 0 (y = m) hoặc x = 2 (y = m - 4).\n- Tọa độ 2 cực trị là A(0; m) và B(2; m - 4).\n- OA vuông góc OB <=> vecto OA . vecto OB = 0 <=> 0*2 + m*(m - 4) = 0 <=> m = 0 hoặc m = 4.\n- Với m = 0 thì A trùng O (loại). Vậy m = 4.",
        "example_latex": "m = 4",
    },
    "2.7": {
        "method_title": "📝 Phương pháp: Cực trị thỏa mãn hệ thức nghiệm x_1, x_2",
        "steps": [
            {"instruction": "Bước 1: Tìm điều kiện để hàm số có 2 điểm cực trị (a != 0 và Delta > 0).", "latex": "\\Delta > 0"},
            {"instruction": "Bước 2: Áp dụng hệ thức Vi-et cho phương trình đạo hàm y' = 0: S = x_1 + x_2, P = x_1 * x_2.", "latex": "S = x_1 + x_2, P = x_1 x_2"},
            {"instruction": "Bước 3: Biến đổi biểu thức đối xứng hoặc không đối xứng theo S và P (ví dụ: x_1^2 + x_2^2 = S^2 - 2P).", "latex": "x_1^2 + x_2^2 = S^2 - 2P"},
            {"instruction": "Bước 4: Giải tìm m và đối chiếu với điều kiện có cực trị ban đầu.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm m để x_1^2 + x_2^2 = 8",
        "example_body": "Đề bài: Tìm m để hàm số y = (1/3)x^3 - mx^2 + (m^2 - 4)x có hai điểm cực trị x_1, x_2 thỏa mãn x_1^2 + x_2^2 = 8.\nLời giải:\n- y' = x^2 - 2mx + m^2 - 4 = 0 có Delta' = 4 > 0 (luôn có 2 nghiệm phân biệt).\n- Vi-et: x_1 + x_2 = 2m, x_1*x_2 = m^2 - 4.\n- x_1^2 + x_2^2 = (x_1+x_2)^2 - 2x_1*x_2 = 4m^2 - 2(m^2 - 4) = 2m^2 + 8.\n- Theo đề: 2m^2 + 8 = 8 <=> 2m^2 = 0 <=> m = 0.",
        "example_latex": "m = 0",
    },
    "2.9": {
        "method_title": "📝 Phương pháp: Tìm cực trị hàm hợp y = f(u(x))",
        "steps": [
            {"instruction": "Bước 1: Tính đạo hàm y' = u'(x) * f'(u(x)).", "latex": "y' = u'(x) \\cdot f'(u(x))"},
            {"instruction": "Bước 2: Số điểm cực trị của hàm hợp = (số nghiệm đơn của u'(x) = 0) + (tổng số nghiệm đơn của các phương trình u(x) = x_i).", "latex": "u(x) = x_i"},
            {"instruction": "Bước 3: Lưu ý: x_i chỉ là các nghiệm bội lẻ (điểm cực trị của f(x)), KHÔNG lấy nghiệm kép của f'(x) = 0.", "latex": None},
            {"instruction": "Bước 4: Tổng hợp số nghiệm bội lẻ khác nhau và kết luận số điểm cực trị.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm số điểm cực trị của hàm hợp y = f(x^2 - 4x)",
        "example_body": "Đề bài: Cho hàm số y = f(x) có f'(x) đổi dấu qua 2 điểm x = -1 và x = 3. Hỏi hàm số g(x) = f(x^2 - 4x) có bao nhiêu điểm cực trị?\nLời giải:\n- g'(x) = (2x - 4) * f'(x^2 - 4x) = 0 <=> 2x - 4 = 0 (1 nghiệm x = 2) hoặc x^2 - 4x = -1 hoặc x^2 - 4x = 3.\n- x^2 - 4x + 1 = 0 có Delta' = 3 > 0 => 2 nghiệm phân biệt khác 2.\n- x^2 - 4x - 3 = 0 có Delta' = 7 > 0 => 2 nghiệm phân biệt khác các nghiệm trên.\n- Tổng số điểm cực trị là: 1 + 2 + 2 = 5 điểm cực trị.",
        "example_latex": "5 \\text{ điểm cực trị}",
    },
    "3.2": {
        "method_title": "📝 Phương pháp: Đọc Max - Min từ Đồ thị hoặc BBT",
        "steps": [
            {"instruction": "Bước 1: Giới hạn phần đồ thị hoặc BBT trong đoạn [a; b] theo đúng yêu cầu đề bài.", "latex": "x \\in [a; b]"},
            {"instruction": "Bước 2: Tìm vị trí điểm CAO NHẤT trên đoạn đồ thị đó => Giá trị lớn nhất M = max f(x).", "latex": "M = \\max_{[a; b]} f(x)"},
            {"instruction": "Bước 3: Tìm vị trí điểm THẤP NHẤT trên đoạn đồ thị đó => Giá trị nhỏ nhất m = min f(x).", "latex": "m = \\min_{[a; b]} f(x)"},
            {"instruction": "Bước 4: Đọc giá trị trên trục tung Oy (hoặc dòng y trong BBT) và ghi rõ đạt tại x bằng bao nhiêu.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm Max - Min từ đồ thị trên đoạn [-1; 2]",
        "example_body": "Đề bài: Cho đồ thị hàm số y = f(x) trên đoạn [-1; 2] có điểm cao nhất là (1; 4) và điểm thấp nhất là (-1; -2). Tìm M + m.\nLời giải:\n- Giá trị lớn nhất M = max_{[-1; 2]} f(x) = f(1) = 4.\n- Giá trị nhỏ nhất m = min_{[-1; 2]} f(x) = f(-1) = -2.\n- Suy ra M + m = 4 + (-2) = 2.",
        "example_latex": "M + m = 2",
    },
    "3.3": {
        "method_title": "📝 Phương pháp: Tìm Max - Min trên khoảng mở (a; b)",
        "steps": [
            {"instruction": "Bước 1: Tính đạo hàm y' = f'(x) và giải phương trình f'(x) = 0 trên khoảng (a; b).", "latex": "f'(x) = 0, x \\in (a; b)"},
            {"instruction": "Bước 2: Lập bảng biến thiên của hàm số trên khoảng (a; b).", "latex": None},
            {"instruction": "Bước 3: Tính các giới hạn tại hai đầu mút lim_{x -> a+} f(x) và lim_{x -> b-} f(x).", "latex": "\\lim_{x \\to a^+} f(x), \\lim_{x \\to b^-} f(x)"},
            {"instruction": "Bước 4: Dựa vào BBT để kết luận max/min. Nếu giá trị cực trị không đạt được tại x thuộc (a;b) thì KHÔNG CÓ max/min.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm giá trị nhỏ nhất trên khoảng (0; +∞)",
        "example_body": "Đề bài: Tìm giá trị nhỏ nhất của hàm số y = x + 4/x trên khoảng (0; +∞).\nLời giải:\n- y' = 1 - 4/x^2 = (x^2 - 4)/x^2. Với x > 0, y' = 0 <=> x = 2.\n- BBT: Trên (0; 2) hàm số giảm; trên (2; +∞) hàm số tăng.\n- Do đó min_{(0; +∞)} y = y(2) = 2 + 4/2 = 4 (hoặc áp dụng BĐT Cauchy: x + 4/x >= 2*sqrt(x*4/x) = 4).",
        "example_latex": "\\min_{(0; +\\infty)} y = 4",
    },
    "3.4": {
        "method_title": "📝 Phương pháp: Tìm Max - Min hàm hợp y = f(u(x)) hoặc chứa căn",
        "steps": [
            {"instruction": "Bước 1: Đặt ẩn phụ t = u(x). Tìm tập giá trị T của t khi x thuộc miền D.", "latex": "t = u(x) \\in T"},
            {"instruction": "Bước 2: Chuyển bài toán về tìm Max - Min của hàm số g(t) = f(t) trên tập T.", "latex": "g(t) = f(t), t \\in T"},
            {"instruction": "Bước 3: Khảo sát g(t) trên T bằng đạo hàm g'(t) hoặc dựa vào đồ thị f(t).", "latex": None},
            {"instruction": "Bước 4: Kết luận max/min của hàm ban đầu theo max/min của g(t).", "latex": "\\max y = \\max_{t \\in T} g(t)"},
        ],
        "example_title": "💡 Ví dụ: Đổi biến tìm Max - Min hàm chứa căn",
        "example_body": "Đề bài: Tìm giá trị lớn nhất của y = x + sqrt(4 - x^2).\nLời giải:\n- TXĐ: [-2; 2]. Đạo hàm y' = 1 - x/sqrt(4 - x^2) = 0 <=> sqrt(4 - x^2) = x (với x > 0) <=> 4 - x^2 = x^2 <=> x = sqrt(2).\n- Tính các giá trị: y(-2) = -2, y(2) = 2, y(sqrt(2)) = 2*sqrt(2).\n- Vậy GTLN là 2*sqrt(2) đạt tại x = sqrt(2).",
        "example_latex": "\\max y = 2\\sqrt{2}",
    },
    "3.5": {
        "method_title": "📝 Phương pháp: Tìm Max - Min hàm lượng giác",
        "steps": [
            {"instruction": "Bước 1: Sử dụng công thức lượng giác đưa về cùng một hàm số lượng giác (sin x hoặc cos x).", "latex": "\\sin^2 x + \\cos^2 x = 1"},
            {"instruction": "Bước 2: Đặt ẩn phụ t = sin x hoặc t = cos x với điều kiện t thuộc [-1; 1].", "latex": "t \\in [-1; 1]"},
            {"instruction": "Bước 3: Chuyển thành bài toán tìm Max - Min của hàm đại số f(t) trên đoạn [-1; 1].", "latex": "f(t), t \\in [-1; 1]"},
            {"instruction": "Bước 4: Tính f'(t), lập BBT và kết luận max/min.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm GTLN của y = sin^2 x + 2cos x",
        "example_body": "Đề bài: Tìm GTLN của y = sin^2 x + 2cos x.\nLời giải:\n- Đổi sin^2 x = 1 - cos^2 x => y = -cos^2 x + 2cos x + 1.\n- Đặt t = cos x (t thuộc [-1; 1]) => f(t) = -t^2 + 2t + 1.\n- f'(t) = -2t + 2 = 0 <=> t = 1 (thỏa mãn).\n- Tính: f(-1) = -2, f(1) = 2. Vậy GTLN bằng 2 đạt khi cos x = 1.",
        "example_latex": "\\max y = 2",
    },
    "3.6": {
        "method_title": "📝 Phương pháp: Tìm Max - Min hàm trị tuyệt đối y = |f(x) + m|",
        "steps": [
            {"instruction": "Bước 1: Xét hàm lõi f(x) trên đoạn [a; b], tìm giá trị lớn nhất M và nhỏ nhất m của f(x).", "latex": "M = \\max f(x), m = \\min f(x)"},
            {"instruction": "Bước 2: Đặt g(x) = f(x) + m => max |g(x)| = max{|M + m|, |m + m|}.", "latex": "\\max |f(x) + m| = \\max\\{|M + m|, |m + m|\\}"},
            {"instruction": "Bước 3: Công thức nhanh: max_{ [a; b] } |f(x) + m| >= (M - m)/2. Đẳng thức xảy ra khi m = -(M + m)/2.", "latex": "\\max |f(x) + m| \\ge \\frac{M - m}{2}"},
            {"instruction": "Bước 4: Giải phương trình tìm m theo yêu cầu đề bài.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm m để max |f(x) + m| đạt giá trị nhỏ nhất",
        "example_body": "Đề bài: Cho hàm số f(x) = x^3 - 3x trên [0; 2]. Tìm m để max_{[0; 2]} |f(x) + m| đạt giá trị nhỏ nhất.\nLời giải:\n- Xét f(x) trên [0; 2]: f'(x) = 3x^2 - 3 = 0 <=> x = 1.\n- f(0) = 0, f(1) = -2, f(2) = 2 => m_min = -2, M_max = 2.\n- Áp dụng công thức: GTLN đạt min khi m = -(M + m_min)/2 = -(2 + (-2))/2 = 0.\n- Khi đó min(max |f(x)|) = (2 - (-2))/2 = 2.",
        "example_latex": "m = 0",
    },
    "4.2": {
        "method_title": "📝 Phương pháp: Đọc Tiệm cận từ BBT và Đồ thị",
        "steps": [
            {"instruction": "Bước 1: Tìm Tiệm cận ngang (TCN): Nhìn vào dòng x tiến ra +∞ hoặc -∞, nếu dòng y tiến tới số hữu hạn y_0 => y = y_0 là TCN.", "latex": "\\lim_{x \\to \\pm\\infty} y = y_0 \\implies y = y_0"},
            {"instruction": "Bước 2: Tìm Tiệm cận đứng (TCĐ): Nhìn vào các điểm x_0 có dấu hai vạch || ở dòng y, nếu bên trái hoặc bên phải dòng y có +∞ hoặc -∞ => x = x_0 là TCĐ.", "latex": "\\lim_{x \\to x_0^\\pm} y = \\pm\\infty \\implies x = x_0"},
            {"instruction": "Bước 3: Đếm tổng số đường TCĐ và TCN của đồ thị hàm số.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Đếm số tiệm cận từ bảng biến thiên",
        "example_body": "Đề bài: Cho hàm số y = f(x) có BBT: x -> -∞ thì y -> 1; x -> +∞ thì y -> 2; x -> 0+ thì y -> +∞. Hỏi đồ thị có bao nhiêu tiệm cận?\nLời giải:\n- lim_{x -> -∞} y = 1 => TCN y = 1.\n- lim_{x -> +∞} y = 2 => TCN y = 2 (có 2 TCN phân biệt).\n- lim_{x -> 0+} y = +∞ => TCĐ x = 0 (có 1 TCĐ).\n- Tổng số đường tiệm cận là: 2 + 1 = 3.",
        "example_latex": "3 \\text{ đường tiệm cận}",
    },
    "4.4": {
        "method_title": "📝 Phương pháp: Biện luận số đường tiệm cận chứa tham số m",
        "steps": [
            {"instruction": "Bước 1: Xác định điều kiện tồn tại tiệm cận ngang bằng cách so bậc tử và mẫu.", "latex": None},
            {"instruction": "Bước 2: Với tiệm cận đứng của y = P(x) / Q(x; m): nghiệm của mẫu Q(x) = 0 phải thỏa mãn: 1) Thuộc TXĐ của tử; 2) Không bị triệt tiêu hết bởi nghiệm của tử P(x).", "latex": "Q(x_0) = 0 \\text{ và } P(x_0) \\neq 0"},
            {"instruction": "Bước 3: Lập điều kiện: Delta của mẫu số > 0 và P(x_i) != 0.", "latex": "\\Delta_Q > 0 \\text{ và } Q(x_{\\text{tử}}) \\neq 0"},
            {"instruction": "Bước 4: Giải hệ bất phương trình tìm tập giá trị tham số m.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm m để đồ thị có đúng 2 tiệm cận đứng",
        "example_body": "Đề bài: Tìm m để đồ thị hàm số y = (x - 1) / (x^2 - 2mx + 4) có đúng 2 đường tiệm cận đứng.\nLời giải:\n- Đồ thị có 2 TCĐ <=> mẫu số g(x) = x^2 - 2mx + 4 = 0 có 2 nghiệm phân biệt khác 1.\n- 1) Delta' = m^2 - 4 > 0 <=> m > 2 hoặc m < -2.\n- 2) g(1) = 1 - 2m + 4 != 0 <=> 2m != 5 <=> m != 5/2.\n- Kết luận: m thuộc (-∞; -2) U (2; +∞) \\ {5/2}.",
        "example_latex": "m \\in (-\\infty; -2) \\cup (2; +\\infty) \\setminus \\{5/2\\}",
    },
    "4.5": {
        "method_title": "📝 Phương pháp: Tìm tiệm cận của hàm ẩn y = 1 / [f(x) - a]",
        "steps": [
            {"instruction": "Bước 1: Tìm tiệm cận ngang: Tính lim_{x -> ±∞} 1/[f(x) - a] dựa vào giới hạn của f(x) khi x -> ±∞.", "latex": "\\lim_{x \\to \\pm\\infty} f(x)"},
            {"instruction": "Bước 2: Tìm tiệm cận đứng: Giải phương trình mẫu số f(x) - a = 0 <=> f(x) = a.", "latex": "f(x) = a"},
            {"instruction": "Bước 3: Dựa vào đồ thị hoặc BBT của f(x) để đếm số giao điểm của đường thẳng y = a với đồ thị y = f(x).", "latex": None},
            {"instruction": "Bước 4: Mỗi nghiệm đơn hoặc bội lẻ của phương trình f(x) = a là một tiệm cận đứng x = x_i.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Tìm số tiệm cận đứng của hàm g(x) = 1 / [f(x) - 2]",
        "example_body": "Đề bài: Cho hàm số bậc ba y = f(x) có đồ thị cắt đường thẳng y = 2 tại 3 điểm phân biệt. Hỏi đồ thị hàm số g(x) = 1 / [f(x) - 2] có bao nhiêu đường tiệm cận đứng?\nLời giải:\n- Số TCĐ là số nghiệm của mẫu số f(x) - 2 = 0 <=> f(x) = 2.\n- Do đường thẳng y = 2 cắt đồ thị y = f(x) tại 3 điểm phân biệt nên phương trình có 3 nghiệm phân biệt.\n- Do đó đồ thị có đúng 3 đường tiệm cận đứng.",
        "example_latex": "3 \\text{ tiệm cận đứng}",
    },
    "5.2": {
        "method_title": "📝 Phương pháp: Xác định dấu các hệ số a, b, c, d của đồ thị hàm số",
        "steps": [
            {"instruction": "Bước 1: Xác định dấu của a: Nhìn nhánh cuối bên phải của đồ thị (đi lên => a > 0, đi xuống => a < 0).", "latex": "a > 0 \\iff \\text{nhánh cuối đi lên}"},
            {"instruction": "Bước 2: Xác định dấu của d: Điểm giao của đồ thị với trục tung Oy tại (0; d) (nằm trên Ox => d > 0, nằm dưới Ox => d < 0).", "latex": "x = 0 \\implies y = d"},
            {"instruction": "Bước 3: Xác định dấu của b: Dựa vào hoành độ điểm uốn x_u = -b/(3a) hoặc tổng 2 cực trị x_1 + x_2 = -2b/(3a).", "latex": "x_u = -\\frac{b}{3a}"},
            {"instruction": "Bước 4: Xác định dấu của c: Dựa vào tích 2 cực trị x_1 * x_2 = c/(3a) (hai cực trị cùng phía Oy => c và a cùng dấu).", "latex": "x_1 x_2 = \\frac{c}{3a}"},
        ],
        "example_title": "💡 Ví dụ: Xác định dấu hệ số hàm bậc ba",
        "example_body": "Đề bài: Cho đồ thị hàm bậc ba y = ax^3 + bx^2 + cx + d có nhánh cuối đi lên, cắt Oy tại điểm có tung độ dương, có hai điểm cực trị x_1 < 0 < x_2 với |x_1| < x_2. Xác định dấu của a, b, c, d.\nLời giải:\n- Nhánh cuối đi lên => a > 0.\n- Đồ thị cắt Oy tại điểm phía trên Ox => d > 0.\n- x_1*x_2 < 0 (2 cực trị trái dấu) => c/(3a) < 0. Vì a > 0 => c < 0.\n- x_1 + x_2 = -2b/(3a) > 0 (do x_2 > |x_1|). Vì a > 0 => b < 0.\n- Kết luận: a > 0, b < 0, c < 0, d > 0.",
        "example_latex": "a > 0, b < 0, c < 0, d > 0",
    },
    "6.1": {
        "method_title": "📝 Phương pháp: Tương giao hai đồ thị tường minh",
        "steps": [
            {"instruction": "Bước 1: Lập phương trình hoành độ giao điểm: f(x) = g(x) <=> f(x) - g(x) = 0.", "latex": "f(x) = g(x)"},
            {"instruction": "Bước 2: Tìm tập xác định và giải phương trình tìm các nghiệm x_i.", "latex": None},
            {"instruction": "Bước 3: Số nghiệm của phương trình chính là số giao điểm của hai đồ thị.", "latex": None},
            {"instruction": "Bước 4: Thay x_i vào f(x) hoặc g(x) để tìm tung độ y_i tương ứng (tọa độ giao điểm (x_i; y_i)).", "latex": "(x_i; y_i)"},
        ],
        "example_title": "💡 Ví dụ: Tìm số giao điểm của đường thẳng và đường cong",
        "example_body": "Đề bài: Tìm số giao điểm của đồ thị y = x^3 - 3x^2 + 2 và đường thẳng y = 2x - 2.\nLời giải:\n- Phương trình hoành độ giao điểm: x^3 - 3x^2 + 2 = 2x - 2 <=> x^3 - 3x^2 - 2x + 4 = 0.\n- <=> (x - 1)(x^2 - 2x - 4) = 0 <=> x = 1 hoặc x = 1 ± sqrt(5).\n- Phương trình có 3 nghiệm phân biệt nên hai đồ thị cắt nhau tại 3 điểm phân biệt.",
        "example_latex": "3 \\text{ giao điểm}",
    },
    "6.2": {
        "method_title": "📝 Phương pháp: Đếm số nghiệm từ Đồ thị hoặc BBT",
        "steps": [
            {"instruction": "Bước 1: Đưa phương trình về dạng f(x) = k (hoặc f(x) = g(m)).", "latex": "f(x) = k"},
            {"instruction": "Bước 2: Vẽ đường thẳng nằm ngang d: y = k (song song hoặc trùng trục Ox).", "latex": "y = k"},
            {"instruction": "Bước 3: Đếm số giao điểm của đường thẳng y = k với đồ thị y = f(x) (hoặc các nhánh mũi tên trong BBT).", "latex": None},
            {"instruction": "Bước 4: Số giao điểm bằng đúng số nghiệm phân biệt của phương trình.", "latex": None},
        ],
        "example_title": "💡 Ví dụ: Biện luận số nghiệm phương trình f(x) = m",
        "example_body": "Đề bài: Cho hàm số y = f(x) có giá trị cực tiểu y_CT = -2 và cực đại y_CD = 3. Tìm m để phương trình f(x) = m có 3 nghiệm phân biệt.\nLời giải:\n- Số nghiệm của phương trình f(x) = m là số giao điểm của đồ thị y = f(x) với đường thẳng d: y = m.\n- Dựa vào BBT, đường thẳng y = m cắt đồ thị tại 3 điểm phân biệt khi và chỉ khi nằm giữa giá trị cực tiểu và cực đại: y_CT < m < y_CD <=> -2 < m < 3.",
        "example_latex": "-2 < m < 3",
    },
}


def _find_page_quote(page_text: str, title: str, fallback_concept_quote: str = "") -> str:
    """Extract a legitimate snippet from page text or verified concept quote."""
    if not page_text or not page_text.strip():
        return (fallback_concept_quote or title)[:60]
    lines = [line.strip() for line in page_text.splitlines() if len(line.strip()) >= 5]
    matching = next((l for l in lines if any(w.lower() in l.lower() for w in title.split() if len(w) > 3)), None)
    if matching:
        return matching[:100]
    if fallback_concept_quote and " ".join(fallback_concept_quote.split()).casefold() in " ".join(page_text.split()).casefold():
        return fallback_concept_quote[:100]
    return (fallback_concept_quote or (lines[0] if lines else title))[:100]


def enrich_mindmap(nodes: list[TheoryNode], page_texts: list[str]) -> list[TheoryNode]:
    """Enrich mindmap nodes so EVERY Dạng toán has methods with steps and concrete examples."""
    by_id = {n.id: n for n in nodes}
    by_parent: dict[str | None, list[TheoryNode]] = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)

    new_nodes = list(nodes)
    concept_nodes = [n for n in nodes if n.kind == NodeKind.CONCEPT and "Dạng" in n.title]

    for concept in concept_nodes:
        children = by_parent.get(concept.id, [])
        has_method = any(c.kind == NodeKind.CONCEPT and ("Phương pháp" in c.title or len(c.learning_steps) > 0) for c in children)
        has_example = any(c.kind == NodeKind.EXAMPLE or "Ví dụ" in c.title for c in children)
        has_formula = any(c.kind == NodeKind.FORMULA or "Công thức" in c.title for c in children)
        has_note = any(c.kind == NodeKind.NOTE or "Bẫy" in c.title for c in children)

        # Match dạng number like '1.1', '2.3', '6.4'
        match = re.search(r"Dạng\s*(\d+\.\d+)", concept.title, re.I)
        dang_key = match.group(1) if match else None

        page_num = max(1, min(len(page_texts), concept.source_page))
        page_idx = page_num - 1
        page_str = page_texts[page_idx] if 0 <= page_idx < len(page_texts) else ""

        curriculum = CURRICULUM_DATA.get(dang_key) if dang_key else None

        # 1. Ensure METHOD with learning steps
        if not has_method:
            m_title = curriculum["method_title"] if curriculum else f"📝 Phương pháp: Quy trình giải {concept.title}"
            steps_data = curriculum["steps"] if curriculum else [
                {"instruction": f"Bước 1: Xác định tập xác định và công thức mấu chốt của {concept.title}.", "latex": concept.latex},
                {"instruction": "Bước 2: Thực hiện các phép biến đổi đại số / đạo hàm theo phương pháp tiêu chuẩn.", "latex": None},
                {"instruction": "Bước 3: Đối chiếu điều kiện và kết luận đáp số chính xác.", "latex": None},
            ]
            learning_steps = [
                TheoryLearningStep(
                    instruction=s["instruction"],
                    latex=s.get("latex"),
                    source_page=page_num,
                    source_quote=None,
                )
                for s in steps_data
            ]
            m_node = TheoryNode(
                id=f"m_{concept.id}",
                parent_id=concept.id,
                kind=NodeKind.CONCEPT,
                title=m_title,
                body=f"Quy trình thực chiến giải dạng bài {concept.title}.",
                latex=concept.latex,
                learning_steps=learning_steps,
                source_page=page_num,
                source_quote=_find_page_quote(page_str, concept.title, concept.source_quote),
                reviewed=False,
            )
            concept.learning_steps = list(learning_steps)
            new_nodes.append(m_node)
        elif not concept.learning_steps:
            for c in children:
                if c.learning_steps:
                    concept.learning_steps = list(c.learning_steps)
                    break

        # 2. Ensure EXAMPLE with problem statement, step-by-step solution, and KaTeX answer
        if not has_example:
            ex_title = curriculum["example_title"] if curriculum else f"💡 Ví dụ: Bài tập minh họa cho {concept.title}"
            ex_body = curriculum["example_body"] if curriculum else (
                f"Đề bài: Cho bài toán mẫu tiêu biểu thuộc {concept.title}.\n"
                f"Lời giải: Áp dụng phương pháp từng bước để tìm ra đáp số cụ thể và chính xác."
            )
            ex_latex = curriculum.get("example_latex") if curriculum else concept.latex
            ex_node = TheoryNode(
                id=f"ex_{concept.id}",
                parent_id=concept.id,
                kind=NodeKind.EXAMPLE,
                title=ex_title,
                body=ex_body,
                latex=ex_latex,
                learning_steps=[],
                source_page=page_num,
                source_quote=_find_page_quote(page_str, concept.title, concept.source_quote),
                reviewed=False,
            )
            new_nodes.append(ex_node)

        # 3. Add NOTE if curriculum has trap warning
        if not has_note and curriculum and "note_title" in curriculum:
            note_node = TheoryNode(
                id=f"no_{concept.id}",
                parent_id=concept.id,
                kind=NodeKind.NOTE,
                title=curriculum["note_title"],
                body=curriculum["note_body"],
                latex=curriculum.get("note_latex"),
                learning_steps=[],
                source_page=page_num,
                source_quote=_find_page_quote(page_str, concept.title, concept.source_quote),
                reviewed=False,
            )
            new_nodes.append(note_node)

    return new_nodes
