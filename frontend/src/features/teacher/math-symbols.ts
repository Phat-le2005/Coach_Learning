export interface MathSymbol {
  id: string;
  label: string;
  latex: string;
  insert: string;
  keywords?: string;
}
export interface MathSymbolGroup { id: string; label: string; symbols: MathSymbol[]; }
const key = (id: string, label: string, latex: string, insert = latex, keywords = ""): MathSymbol => ({ id, label, latex, insert, keywords });

const greek = [
  ["alpha", "alpha", "\\alpha"], ["beta", "beta", "\\beta"], ["gamma", "gamma", "\\gamma"],
  ["delta", "delta", "\\delta"], ["epsilon", "epsilon", "\\epsilon"], ["varepsilon", "epsilon biến thể", "\\varepsilon"],
  ["zeta", "zeta", "\\zeta"], ["eta", "eta", "\\eta"], ["theta", "theta", "\\theta"], ["vartheta", "theta biến thể", "\\vartheta"],
  ["iota", "iota", "\\iota"], ["kappa", "kappa", "\\kappa"], ["lambda", "lambda", "\\lambda"],
  ["mu", "mu", "\\mu"], ["nu", "nu", "\\nu"], ["xi", "xi", "\\xi"], ["omicron", "omicron", "o"],
  ["pi", "pi", "\\pi"], ["varpi", "pi biến thể", "\\varpi"], ["rho", "rho", "\\rho"], ["varrho", "rho biến thể", "\\varrho"],
  ["sigma", "sigma", "\\sigma"], ["varsigma", "sigma cuối từ", "\\varsigma"], ["tau", "tau", "\\tau"],
  ["upsilon", "upsilon", "\\upsilon"], ["phi", "phi", "\\phi"], ["varphi", "phi biến thể", "\\varphi"],
  ["chi", "chi", "\\chi"], ["psi", "psi", "\\psi"], ["omega", "omega", "\\omega"],
] as const;
const greekUpper = [
  ["Alpha", "A"], ["Beta", "B"], ["Gamma", "\\Gamma"], ["Delta", "\\Delta"], ["Epsilon", "E"],
  ["Zeta", "Z"], ["Eta", "H"], ["Theta", "\\Theta"], ["Iota", "I"], ["Kappa", "K"],
  ["Lambda", "\\Lambda"], ["Mu", "M"], ["Nu", "N"], ["Xi", "\\Xi"], ["Omicron", "O"],
  ["Pi", "\\Pi"], ["Rho", "P"], ["Sigma", "\\Sigma"], ["Tau", "T"], ["Upsilon", "\\Upsilon"],
  ["Phi", "\\Phi"], ["Chi", "X"], ["Psi", "\\Psi"], ["Omega", "\\Omega"],
] as const;

export const MATH_SYMBOL_GROUPS: MathSymbolGroup[] = [
  { id: "common", label: "Thường dùng", symbols: [
    key("fraction", "Phân số", "\\frac{a}{b}", "\\frac{#0}{#?}", "chia tử mẫu"),
    key("sqrt", "Căn bậc hai", "\\sqrt{x}", "\\sqrt{#0}"),
    key("nth-root", "Căn bậc n", "\\sqrt[n]{x}", "\\sqrt[#?]{#0}"),
    key("square", "Bình phương", "x^2", "#0^{2}"), key("power", "Lũy thừa", "x^n", "#0^{#?}"),
    key("subscript", "Chỉ số dưới", "x_i", "#0_{#?}"),
    key("times", "Nhân", "\\times"), key("divide", "Chia", "\\div"), key("dot", "Tích", "\\cdot"),
    key("plus-minus", "Cộng trừ", "\\pm"), key("minus-plus", "Trừ cộng", "\\mp"),
    key("absolute", "Giá trị tuyệt đối", "|x|", "\\left|#0\\right|"),
    key("brackets", "Ngoặc tròn", "(x)", "\\left(#0\\right)"),
    key("square-brackets", "Ngoặc vuông", "[x]", "\\left[#0\\right]"),
    key("braces", "Ngoặc nhọn", "\\{x\\}", "\\left\\{#0\\right\\}"),
    key("infinity", "Vô cực", "\\infty"), key("percent", "Phần trăm", "\\%"),
    key("factorial", "Giai thừa", "n!", "#0!"), key("binomial", "Tổ hợp", "\\binom{n}{k}", "\\binom{#0}{#?}"),
  ] },
  { id: "calculus", label: "Đạo hàm · Tích phân", symbols: [
    key("integral", "Tích phân", "\\int", "\\int #0\\,\\mathrm{d}x"),
    key("definite-integral", "Tích phân có cận", "\\int_a^b f(x)\\,\\mathrm{d}x", "\\int_{#?}^{#?} #0\\,\\mathrm{d}x"),
    key("double-integral", "Tích phân kép", "\\iint", "\\iint #0\\,\\mathrm{d}x\\,\\mathrm{d}y"),
    key("triple-integral", "Tích phân ba lớp", "\\iiint", "\\iiint #0\\,\\mathrm{d}V"),
    key("closed-integral", "Tích phân đường kín", "\\oint", "\\oint #0\\,\\mathrm{d}s"),
    key("prime", "Đạo hàm dấu phẩy", "f'(x)", "#0^{\\prime}"),
    key("second-prime", "Đạo hàm bậc hai", "f''(x)", "#0^{\\prime\\prime}"),
    key("derivative", "Đạo hàm theo x", "\\frac{\\mathrm{d}y}{\\mathrm{d}x}", "\\frac{\\mathrm{d}#0}{\\mathrm{d}x}"),
    key("nth-derivative", "Đạo hàm bậc n", "\\frac{\\mathrm{d}^ny}{\\mathrm{d}x^n}", "\\frac{\\mathrm{d}^{#?}#0}{\\mathrm{d}x^{#?}}"),
    key("partial", "Đạo hàm riêng", "\\frac{\\partial f}{\\partial x}", "\\frac{\\partial #0}{\\partial x}"),
    key("partial-symbol", "Ký hiệu đạo hàm riêng", "\\partial"), key("nabla", "Nabla gradient", "\\nabla"),
    key("limit", "Giới hạn", "\\lim_{x\\to a}f(x)", "\\lim_{x\\to #?}#0"),
    key("sum", "Tổng sigma", "\\sum_{i=1}^{n}x_i", "\\sum_{#?}^{#?}#0"),
    key("product", "Tích liên tiếp", "\\prod_{i=1}^{n}x_i", "\\prod_{#?}^{#?}#0"),
    key("differential", "Vi phân", "\\mathrm{d}x"),
  ] },
  { id: "functions", label: "Hàm · Lượng giác", symbols: [
    ...["sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "ln", "log", "exp"].map((name) => key(`fn-${name}`, name, `\\${name} x`, `\\${name}\\left(#0\\right)`)),
    key("log-base", "Logarit cơ số", "\\log_a x", "\\log_{#?}\\left(#0\\right)"),
    key("exponential", "Hàm mũ e", "e^x", "e^{#0}"),
    key("minimum", "Giá trị nhỏ nhất", "\\min"), key("maximum", "Giá trị lớn nhất", "\\max"),
    key("floor", "Phần nguyên dưới", "\\lfloor x\\rfloor", "\\left\\lfloor #0\\right\\rfloor"),
    key("ceiling", "Phần nguyên trên", "\\lceil x\\rceil", "\\left\\lceil #0\\right\\rceil"),
  ] },
  { id: "sets", label: "Quan hệ · Tập hợp", symbols: [
    ...[["equal", "Bằng", "="], ["not-equal", "Không bằng", "\\ne"], ["less", "Nhỏ hơn", "<"], ["greater", "Lớn hơn", ">"],
      ["less-equal", "Nhỏ hơn hoặc bằng", "\\le"], ["greater-equal", "Lớn hơn hoặc bằng", "\\ge"], ["approx", "Xấp xỉ", "\\approx"],
      ["equivalent", "Tương đương", "\\Leftrightarrow"], ["implies", "Suy ra", "\\Rightarrow"], ["arrow", "Tiến tới", "\\to"],
      ["belongs", "Thuộc", "\\in"], ["not-belongs", "Không thuộc", "\\notin"], ["subset", "Tập con", "\\subset"],
      ["subset-equal", "Tập con hoặc bằng", "\\subseteq"], ["union", "Hợp tập hợp", "\\cup"], ["intersection", "Giao tập hợp", "\\cap"],
      ["difference", "Hiệu tập hợp", "\\setminus"], ["empty", "Tập rỗng", "\\varnothing"], ["forall", "Với mọi", "\\forall"],
      ["exists", "Tồn tại", "\\exists"], ["not-exists", "Không tồn tại", "\\nexists"], ["and", "Và logic", "\\land"], ["or", "Hoặc logic", "\\lor"],
      ["real", "Số thực", "\\mathbb{R}"], ["natural", "Số tự nhiên", "\\mathbb{N}"], ["integer", "Số nguyên", "\\mathbb{Z}"],
      ["rational", "Số hữu tỉ", "\\mathbb{Q}"], ["complex", "Số phức", "\\mathbb{C}"], ["dots", "Dấu ba chấm", "\\ldots"],
    ].map(([id, label, latex]) => key(id, label, latex)),
  ] },
  { id: "geometry", label: "Hình học · Xác suất", symbols: [
    key("vector", "Vectơ", "\\overrightarrow{AB}", "\\overrightarrow{#0}"),
    key("bar", "Đoạn thẳng hoặc biến cố đối", "\\overline{AB}", "\\overline{#0}"),
    key("angle", "Góc", "\\angle ABC", "\\angle #0"), key("angle-hat", "Góc có mũ", "\\widehat{ABC}", "\\widehat{#0}"),
    key("parallel", "Song song", "\\parallel"), key("perpendicular", "Vuông góc", "\\perp"),
    key("degree", "Độ", "90^{\\circ}", "#0^{\\circ}"),
    key("triangle", "Tam giác", "\\triangle ABC", "\\triangle #0"),
    key("norm", "Độ dài vectơ", "\\lVert u\\rVert", "\\left\\lVert #0\\right\\rVert"),
    key("probability", "Xác suất", "P(A)", "P\\left(#0\\right)"),
    key("conditional", "Xác suất có điều kiện", "P(A\\mid B)", "P\\left(#0\\mid #?\\right)"),
    key("expectation", "Kỳ vọng", "E(X)", "E\\left(#0\\right)"),
    key("variance", "Phương sai", "\\operatorname{Var}(X)", "\\operatorname{Var}\\left(#0\\right)"),
    key("mean", "Giá trị trung bình", "\\overline{x}", "\\overline{#0}"),
    key("matrix", "Ma trận 2 hàng 2 cột", "\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}", "\\begin{pmatrix}#?&#?\\\\#?&#?\\end{pmatrix}"),
    key("cases", "Hệ phương trình", "\\begin{cases}x+y=1\\\\x-y=0\\end{cases}", "\\begin{cases}#?\\\\#?\\end{cases}"),
  ] },
  { id: "greek", label: "Chữ Hy Lạp", symbols: [
    ...greek.map(([id, label, latex]) => key(`greek-${id}`, label, latex, latex, id === "lambda" ? "landa lam đa lamda" : "hy lap")),
    ...greekUpper.map(([name, latex]) => key(`greek-upper-${name}`, `${name} hoa`, latex, latex, "hy lap in hoa")),
  ] },
  { id: "letters", label: "Chữ · Số", symbols: Array.from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789").map((letter) => key(`letter-${letter}`, `Chữ ${letter}`, letter)) },
];

export const QUICK_MATH_KEYS = Array.from("0123456789xyz+-=.,").map((s) => key(`quick-${s}`, s, s));
export function searchMathSymbols(query: string, group: string): MathSymbol[] {
  const fold = (s: string) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/[\\/]/g, "");
  const term = fold(query.trim());
  const symbols = term ? MATH_SYMBOL_GROUPS.flatMap((g) => g.symbols) : MATH_SYMBOL_GROUPS.find((g) => g.id === group)?.symbols ?? [];
  return term ? symbols.filter((s) => fold(`${s.label} ${s.keywords ?? ""} ${s.latex}`).includes(term)) : symbols;
}
