from pathlib import Path
import fitz

def crop_page_region(pdf_path: str, page_number: int, bbox: tuple[float, float, float, float],
                     output_path: str) -> str:
    # bbox dùng tọa độ PDF: (x0, y0, x1, y1), page_number bắt đầu từ 1.
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as doc:
        page = doc[page_number - 1]
        clip = fitz.Rect(*bbox)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
        pix.save(output)
    return str(output)

def make_function_plot_latex(expression: str, xmin: int = -5, xmax: int = 5) -> str:
    # Chỉ dùng với biểu thức đã được kiểm duyệt/chuẩn hóa; không đưa input tùy ý vào LaTeX.
    return r'''\begin{tikzpicture}
\begin{axis}[
  axis lines=middle,
  grid=both,
  xlabel={$x$}, ylabel={$y$},
  xmin=%d, xmax=%d,
  samples=150
]
\addplot[domain=%d:%d] {%s};
\end{axis}
\end{tikzpicture}''' % (xmin, xmax, xmin, xmax, expression)


def image_to_latex(image_path: str, caption: str = "") -> str:
    """Embed a reviewed PDF crop in LaTeX without inventing chart data."""
    path = Path(image_path).as_posix()
    caption_line = f"\n\\caption{{{caption}}}" if caption else ""
    return (
        "\\begin{figure}[h]\n"
        "\\centering\n"
        f"\\includegraphics[width=0.9\\textwidth]{{{path}}}"
        f"{caption_line}\n"
        "\\end{figure}"
    )
