"""Tạo LaTeX từ dữ liệu đã được nhận diện/chuẩn hóa."""
import re

SAFE_EXPRESSION = re.compile(r"^[0-9a-zA-ZxXyY()+\-*/^.=,\s{}]+$")

def expression_to_latex_candidate(expression: str) -> str:
    """
    Chuyển đổi tối thiểu biểu thức ASCII thành candidate LaTeX.
    Không thay thế OCR công thức chuyên dụng hoặc kiểm tra đại số.
    """
    expression = expression.strip()
    if not expression or not SAFE_EXPRESSION.fullmatch(expression):
        raise ValueError("Biểu thức chứa ký tự chưa được hỗ trợ; cần kiểm tra thủ công.")
    return expression.replace("*", r"\\cdot ")

def function_plot_template(expression: str, xmin: int = -5, xmax: int = 5) -> str:
    expr = expression_to_latex_candidate(expression)
    return r"""\\begin{tikzpicture}
\\begin{axis}[
  axis lines=middle,
  grid=both,
  xlabel={$x$}, ylabel={$y$},
  xmin=%d, xmax=%d,
  samples=150
]
\\addplot[domain=%d:%d] {%s};
\\end{axis}
\\end{tikzpicture}""" % (xmin, xmax, xmin, xmax, expr)

def variation_table_template(x_values: list[str], f_values: list[str],
                             derivative_signs: list[str]) -> str:
    """
    Tạo bảng biến thiên dạng array đơn giản từ dữ liệu cấu trúc.
    Dữ liệu đầu vào phải được người dùng/hệ thống kiểm chứng trước.
    """
    if len(x_values) != len(f_values) or len(x_values) != len(derivative_signs):
        raise ValueError("Ba danh sách phải có cùng số phần tử.")
    def row(values):
        return " & ".join(values)
    return (
        r"\\begin{array}{c|%s}" % ("c|" * (len(x_values)-1) + "c")
        + "\n x & " + row(x_values)
        + r"\\"
        + "\n f'(x) & " + row(derivative_signs)
        + r"\\"
        + "\n f(x) & " + row(f_values)
        + r"\\end{array}"
    )
