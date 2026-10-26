"""
Generates the publication-quality 4-page PDF for testing Math OCR engines.
"""

import os
import subprocess
import sys
from pathlib import Path
import fitz

OUTPUT_DIR = Path("d:/CoachLearning")
HTML_PATH = OUTPUT_DIR / "Bo_10_Cau_Hoi_Va_Dap_An_Test_OCR_Toan12.html"
PDF_PATH = OUTPUT_DIR / "Bo_10_Cau_Hoi_Va_Dap_An_Test_OCR_Toan12.pdf"

HTML_CONTENT = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Bộ 10 Bài Toán Thực Nghiệm OCR Toán 12 - EduMS</title>
<style>
  @page {
    size: A4 portrait;
    margin: 12mm 14mm 12mm 14mm;
  }
  * {
    box-sizing: border-box;
  }
  body {
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Times New Roman", Roboto, sans-serif;
    color: #1f2937;
    background: #ffffff;
    line-height: 1.45;
    font-size: 13px;
    margin: 0;
    padding: 0;
  }

  /* Header Table */
  .exam-header {
    width: 100%;
    border-bottom: 2px solid #0f766e;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }
  .header-left {
    text-align: center;
    font-size: 11.5px;
    font-weight: 700;
    color: #0f766e;
    text-transform: uppercase;
    line-height: 1.35;
  }
  .header-right {
    text-align: center;
    font-size: 11.5px;
    font-weight: 700;
    color: #1e3a8a;
    line-height: 1.35;
  }
  .exam-title {
    text-align: center;
    margin: 8px 0 3px;
    font-size: 16.5px;
    font-weight: 800;
    color: #0f172a;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }
  .exam-subtitle {
    text-align: center;
    font-size: 11px;
    color: #475569;
    margin-bottom: 12px;
    font-style: italic;
  }

  /* Section Title */
  .section-banner {
    background: #f0fdf4;
    border-left: 4px solid #10b981;
    padding: 6px 12px;
    font-size: 12.5px;
    font-weight: 800;
    color: #065f46;
    text-transform: uppercase;
    margin: 10px 0 10px;
    border-radius: 0 5px 5px 0;
  }
  .section-banner-sol {
    background: #f0f9ff;
    border-left: 4px solid #0284c7;
    padding: 6px 12px;
    font-size: 12.5px;
    font-weight: 800;
    color: #0369a1;
    text-transform: uppercase;
    margin: 10px 0 12px;
    border-radius: 0 5px 5px 0;
  }

  /* Question Box */
  .question-item {
    margin-bottom: 10px;
    padding: 8px 12px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
  }
  .question-title {
    font-weight: 600;
    color: #0f172a;
    margin-bottom: 4px;
    font-size: 12.8px;
  }
  .question-badge {
    display: inline-block;
    background: #0f766e;
    color: #ffffff;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 10.5px;
    font-weight: 700;
    margin-right: 5px;
  }
  .question-tag {
    display: inline-block;
    background: #f1f5f9;
    color: #475569;
    border: 1px solid #cbd5e1;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    margin-right: 5px;
  }

  /* Options Grid */
  .options-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px 14px;
    margin-top: 6px;
  }
  .options-grid-4 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 1fr;
    gap: 4px 10px;
    margin-top: 6px;
  }
  .option-choice {
    font-size: 12.5px;
    color: #1e293b;
  }
  .opt-label {
    font-weight: 700;
    color: #0f766e;
    margin-right: 3px;
  }

  /* True/False Sub-items */
  .tf-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 6px;
    font-size: 12px;
  }
  .tf-table th, .tf-table td {
    border: 1px solid #cbd5e1;
    padding: 5px 8px;
  }
  .tf-table th {
    background: #f8fafc;
    color: #334155;
    font-weight: 700;
  }

  /* Handwriting Space for OCR Testing */
  .handwriting-box {
    margin-top: 8px;
    border: 1.5px dashed #94a3b8;
    background: #fcfdfe;
    border-radius: 6px;
    padding: 8px 12px;
  }
  .handwriting-label {
    font-size: 10.5px;
    font-weight: 700;
    color: #475569;
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .dotted-line {
    border-bottom: 1px dotted #cbd5e1;
    height: 24px;
    margin-bottom: 2px;
  }

  /* MathML & Math Styling */
  math {
    font-family: "Cambria Math", "Times New Roman", serif;
    font-size: 1.1em;
  }

  /* Explicit Page Break */
  .page-break {
    page-break-after: always;
    break-after: page;
  }

  /* Solution Table */
  .ans-matrix-table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 14px;
    font-size: 12px;
    text-align: center;
  }
  .ans-matrix-table th, .ans-matrix-table td {
    border: 1px solid #cbd5e1;
    padding: 5px 6px;
  }
  .ans-matrix-table th {
    background: #0f766e;
    color: #ffffff;
    font-weight: 700;
  }
  .ans-matrix-table td {
    font-weight: 800;
    color: #0f172a;
  }

  /* Solution Item */
  .solution-item {
    margin-bottom: 11px;
    padding: 8px 12px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
  }
  .solution-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 5px;
    padding-bottom: 3px;
    border-bottom: 1px solid #e2e8f0;
  }
  .solution-correct-ans {
    font-weight: 800;
    color: #047857;
    background: #d1fae5;
    padding: 1px 7px;
    border-radius: 4px;
    font-size: 11px;
  }
  .solution-body {
    font-size: 12.5px;
    color: #334155;
    line-height: 1.5;
  }
  .solution-step {
    margin: 3px 0;
  }

  /* Footer Note */
  .footer-note {
    margin-top: 14px;
    padding-top: 8px;
    border-top: 1px solid #cbd5e1;
    text-align: center;
    font-size: 10.5px;
    color: #64748b;
  }
  .page-num {
    text-align: right;
    font-size: 10px;
    color: #94a3b8;
    margin-top: 6px;
  }
</style>
</head>
<body>

  <!-- =======================================================================
       TRANG 1: ĐỀ BÀI CÂU 1 -> CÂU 6
       ======================================================================= -->
  <table class="exam-header">
    <tr>
      <td class="header-left" style="width: 50%;">
        BỘ GIÁO DỤC VÀ ĐÀO TẠO<br>
        <strong>HỆ THỐNG HỌC TẬP THÔNG MINH EDUMS</strong>
      </td>
      <td class="header-right" style="width: 50%;">
        <strong>TẬP MẪU DỮ LIỆU KIỂM THỬ OCR TOÁN HỌC</strong><br>
        Mã đề: <strong>OCR-MATH12-01</strong>
      </td>
    </tr>
  </table>

  <div class="exam-title">BỘ 10 BÀI TOÁN THỰC NGHIỆM HỆ THỐNG OCR</div>
  <div class="exam-subtitle">
    (Gồm Câu hỏi trắc nghiệm, Đúng/Sai, Tự luận viết tay và Lời giải chi tiết đối soát độ chính xác OCR)
  </div>

  <div class="section-banner">
    PHẦN I: ĐỀ BÀI 10 CÂU HỎI THỰC NGHIỆM
  </div>

  <!-- CÂU 1 -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 1</span>
      <span class="question-tag">Khảo sát hàm số</span>
      <span class="question-tag">Tiệm cận</span>
      Cho hàm số 
      <math display="inline">
        <mi>y</mi><mo>=</mo><mfrac><mrow><mn>2</mn><mi>x</mi><mo>−</mo><mn>1</mn></mrow><mrow><mi>x</mi><mo>+</mo><mn>2</mn></mrow></mfrac>
      </math>. 
      Đường tiệm cận đứng của đồ thị hàm số đã cho có phương trình là:
    </div>
    <div class="options-grid-4">
      <div class="option-choice"><span class="opt-label">A.</span> <math><mi>x</mi><mo>=</mo><mfrac><mn>1</mn><mn>2</mn></mfrac></math></div>
      <div class="option-choice"><span class="opt-label">B.</span> <math><mi>y</mi><mo>=</mo><mn>2</mn></math></div>
      <div class="option-choice"><span class="opt-label">C.</span> <math><mi>x</mi><mo>=</mo><mo>−</mo><mn>2</mn></math></div>
      <div class="option-choice"><span class="opt-label">D.</span> <math><mi>y</mi><mo>=</mo><mo>−</mo><mn>2</mn></math></div>
    </div>
  </div>

  <!-- CÂU 2 -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 2</span>
      <span class="question-tag">Đạo hàm</span>
      <span class="question-tag">Cực trị</span>
      Cho hàm số 
      <math display="inline">
        <mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><msup><mi>x</mi><mn>3</mn></msup><mo>−</mo><mn>3</mn><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo><mn>2</mn>
      </math>. 
      Tọa độ điểm cực đại của đồ thị hàm số là:
    </div>
    <div class="options-grid-4">
      <div class="option-choice"><span class="opt-label">A.</span> <math><mo>(</mo><mn>0</mn><mo>;</mo><mn>2</mn><mo>)</mo></math></div>
      <div class="option-choice"><span class="opt-label">B.</span> <math><mo>(</mo><mn>2</mn><mo>;</mo><mo>−</mo><mn>2</mn><mo>)</mo></math></div>
      <div class="option-choice"><span class="opt-label">C.</span> <math><mo>(</mo><mn>0</mn><mo>;</mo><mn>0</mn><mo>)</mo></math></div>
      <div class="option-choice"><span class="opt-label">D.</span> <math><mo>(</mo><mn>2</mn><mo>;</mo><mn>2</mn><mo>)</mo></math></div>
    </div>
  </div>

  <!-- CÂU 3 -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 3</span>
      <span class="question-tag">Mũ &amp; Logarit</span>
      Nghiệm của phương trình mũ 
      <math display="inline">
        <msup><mn>2</mn><mrow><mn>2</mn><mi>x</mi><mo>−</mo><mn>1</mn></mrow></msup><mo>=</mo><mn>32</mn>
      </math> là:
    </div>
    <div class="options-grid-4">
      <div class="option-choice"><span class="opt-label">A.</span> <math><mi>x</mi><mo>=</mo><mn>2</mn></math></div>
      <div class="option-choice"><span class="opt-label">B.</span> <math><mi>x</mi><mo>=</mo><mn>3</mn></math></div>
      <div class="option-choice"><span class="opt-label">C.</span> <math><mi>x</mi><mo>=</mo><mfrac><mn>5</mn><mn>2</mn></mfrac></math></div>
      <div class="option-choice"><span class="opt-label">D.</span> <math><mi>x</mi><mo>=</mo><mfrac><mn>7</mn><mn>2</mn></mfrac></math></div>
    </div>
  </div>

  <!-- CÂU 4 -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 4</span>
      <span class="question-tag">Vectơ Oxyz</span>
      Trong không gian <math display="inline"><mi>O</mi><mi>x</mi><mi>y</mi><mi>z</mi></math>, 
      cho hai vectơ 
      <math display="inline">
        <mover><mi>a</mi><mo>→</mo></mover><mo>=</mo><mo>(</mo><mn>1</mn><mo>;</mo><mo>−</mo><mn>2</mn><mo>;</mo><mo>−</mo><mn>1</mn><mo>)</mo>
      </math> và 
      <math display="inline">
        <mover><mi>b</mi><mo>→</mo></mover><mo>=</mo><mo>(</mo><mn>2</mn><mo>;</mo><mo>−</mo><mn>4</mn><mo>;</mo><mn>2</mn><mo>)</mo>
      </math>. 
      Tích vô hướng 
      <math display="inline">
        <mover><mi>a</mi><mo>→</mo></mover><mo>⋅</mo><mover><mi>b</mi><mo>→</mo></mover>
      </math> bằng:
    </div>
    <div class="options-grid-4">
      <div class="option-choice"><span class="opt-label">A.</span> <math><mo>−</mo><mn>8</mn></math></div>
      <div class="option-choice"><span class="opt-label">B.</span> <math><mn>8</mn></math></div>
      <div class="option-choice"><span class="opt-label">C.</span> <math><mo>−</mo><mn>12</mn></math></div>
      <div class="option-choice"><span class="opt-label">D.</span> <math><mn>12</mn></math></div>
    </div>
  </div>

  <!-- CÂU 5 -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 5</span>
      <span class="question-tag">Tích phân</span>
      <span class="question-tag">Diện tích hình phẳng</span>
      Diện tích <math><mi>S</mi></math> của hình phẳng giới hạn bởi đồ thị 
      <math display="inline"><mi>y</mi><mo>=</mo><msup><mi>x</mi><mn>2</mn></msup></math> 
      và đường cong 
      <math display="inline"><mi>y</mi><mo>=</mo><mn>8</mn><mo>−</mo><msup><mi>x</mi><mn>2</mn></msup></math> là:
    </div>
    <div class="options-grid-4">
      <div class="option-choice"><span class="opt-label">A.</span> <math><mi>S</mi><mo>=</mo><mn>14</mn></math></div>
      <div class="option-choice"><span class="opt-label">B.</span> <math><mi>S</mi><mo>=</mo><mn>28</mn></math></div>
      <div class="option-choice"><span class="opt-label">C.</span> <math><mi>S</mi><mo>=</mo><mfrac><mn>64</mn><mn>3</mn></mfrac></math></div>
      <div class="option-choice"><span class="opt-label">D.</span> <math><mi>S</mi><mo>=</mo><mfrac><mn>64</mn><mn>5</mn></mfrac></math></div>
    </div>
  </div>

  <!-- CÂU 6 -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 6</span>
      <span class="question-tag">Nguyên hàm</span>
      Tìm họ nguyên hàm của hàm số 
      <math display="inline">
        <mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><msup><mi>e</mi><mi>x</mi></msup><mo>−</mo><mn>2</mn><mi>x</mi>
      </math>:
    </div>
    <div class="options-grid">
      <div class="option-choice"><span class="opt-label">A.</span> <math><mo>∫</mo><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mi>d</mi><mi>x</mi><mo>=</mo><msup><mi>e</mi><mi>x</mi></msup><mo>+</mo><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo><mi>C</mi></math></div>
      <div class="option-choice"><span class="opt-label">B.</span> <math><mo>∫</mo><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mi>d</mi><mi>x</mi><mo>=</mo><msup><mi>e</mi><mi>x</mi></msup><mo>−</mo><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo><mi>C</mi></math></div>
      <div class="option-choice"><span class="opt-label">C.</span> <math><mo>∫</mo><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mi>d</mi><mi>x</mi><mo>=</mo><msup><mi>e</mi><mi>x</mi></msup><mo>−</mo><mn>2</mn><mo>+</mo><mi>C</mi></math></div>
      <div class="option-choice"><span class="opt-label">D.</span> <math><mo>∫</mo><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mi>d</mi><mi>x</mi><mo>=</mo><mfrac><mn>1</mn><mn>2</mn></mfrac><msup><mi>e</mi><mi>x</mi></msup><mo>−</mo><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo><mi>C</mi></math></div>
    </div>
  </div>

  <div class="page-num">Trang 1 / 4</div>
  <div class="page-break"></div>

  <!-- =======================================================================
       TRANG 2: ĐỀ BÀI CÂU 7 -> CÂU 10 (GỒM ĐÚNG/SAI VÀ KHUNG VIẾT TAY)
       ======================================================================= -->
  <!-- CÂU 7 -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 7</span>
      <span class="question-tag">Phương pháp tọa độ</span>
      Trong không gian <math><mi>O</mi><mi>x</mi><mi>y</mi><mi>z</mi></math>, 
      mặt phẳng <math><mo>(</mo><mi>α</mi><mo>)</mo></math> đi qua điểm 
      <math><mi>M</mi><mo>(</mo><mn>1</mn><mo>;</mo><mo>−</mo><mn>2</mn><mo>;</mo><mn>3</mn><mo>)</mo></math> 
      và có vectơ pháp tuyến 
      <math><mover><mi>n</mi><mo>→</mo></mover><mo>=</mo><mo>(</mo><mn>2</mn><mo>;</mo><mn>1</mn><mo>;</mo><mo>−</mo><mn>1</mn><mo>)</mo></math> 
      có phương trình tổng quát là:
    </div>
    <div class="options-grid">
      <div class="option-choice"><span class="opt-label">A.</span> <math><mn>2</mn><mi>x</mi><mo>+</mo><mi>y</mi><mo>−</mo><mi>z</mi><mo>+</mo><mn>3</mn><mo>=</mo><mn>0</mn></math></div>
      <div class="option-choice"><span class="opt-label">B.</span> <math><mn>2</mn><mi>x</mi><mo>+</mo><mi>y</mi><mo>−</mo><mi>z</mi><mo>−</mo><mn>3</mn><mo>=</mo><mn>0</mn></math></div>
      <div class="option-choice"><span class="opt-label">C.</span> <math><mi>x</mi><mo>−</mo><mn>2</mn><mi>y</mi><mo>+</mo><mn>3</mn><mi>z</mi><mo>−</mo><mn>3</mn><mo>=</mo><mn>0</mn></math></div>
      <div class="option-choice"><span class="opt-label">D.</span> <math><mn>2</mn><mi>x</mi><mo>+</mo><mi>y</mi><mo>−</mo><mi>z</mi><mo>+</mo><mn>1</mn><mo>=</mo><mn>0</mn></math></div>
    </div>
  </div>

  <!-- CÂU 8 -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 8</span>
      <span class="question-tag">Xác suất có điều kiện</span>
      Một hộp kín chứa 6 quả bóng màu trắng và 4 quả bóng màu đỏ. 
      Lấy ngẫu nhiên lần lượt không hoàn lại 2 quả bóng. 
      Tính xác suất để quả bóng thứ hai lấy được là màu đỏ, biết rằng quả bóng thứ nhất lấy được là màu trắng:
    </div>
    <div class="options-grid-4">
      <div class="option-choice"><span class="opt-label">A.</span> <math><mfrac><mn>4</mn><mn>9</mn></mfrac></math></div>
      <div class="option-choice"><span class="opt-label">B.</span> <math><mfrac><mn>4</mn><mn>10</mn></mfrac></math></div>
      <div class="option-choice"><span class="opt-label">C.</span> <math><mfrac><mn>3</mn><mn>9</mn></mfrac></math></div>
      <div class="option-choice"><span class="opt-label">D.</span> <math><mfrac><mn>6</mn><mn>9</mn></mfrac></math></div>
    </div>
  </div>

  <!-- CÂU 9: TRẮC NGHIỆM ĐÚNG/SAI 4 Ý -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 9</span>
      <span class="question-tag">Dạng Đúng/Sai 4 ý</span>
      <span class="question-tag">Chuẩn THPT 2025</span>
      Cho hàm số bậc ba 
      <math display="inline">
        <mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><msup><mi>x</mi><mn>3</mn></msup><mo>−</mo><mn>12</mn><mi>x</mi><mo>−</mo><mn>8</mn>
      </math>. 
      Xét tính Đúng / Sai của các khẳng định sau:
    </div>

    <table class="tf-table">
      <thead>
        <tr>
          <th style="width: 8%;">Ý</th>
          <th style="width: 72%;">Khẳng định / Mệnh đề toán học</th>
          <th style="width: 10%; text-align: center;">Đúng</th>
          <th style="width: 10%; text-align: center;">Sai</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td style="font-weight: 700; text-align: center;">a)</td>
          <td>Đạo hàm của hàm số đã cho là <math><msup><mi>f</mi><mo>′</mo></msup><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mn>3</mn><msup><mi>x</mi><mn>2</mn></msup><mo>−</mo><mn>12</mn></math>.</td>
          <td style="text-align: center;">[ &nbsp; ]</td>
          <td style="text-align: center;">[ &nbsp; ]</td>
        </tr>
        <tr>
          <td style="font-weight: 700; text-align: center;">b)</td>
          <td>Phương trình <math><msup><mi>f</mi><mo>′</mo></msup><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mn>0</mn></math> có tập nghiệm là <math><mi>S</mi><mo>=</mo><mo>{</mo><mo>−</mo><mn>2</mn><mo>;</mo><mn>2</mn><mo>}</mo></math>.</td>
          <td style="text-align: center;">[ &nbsp; ]</td>
          <td style="text-align: center;">[ &nbsp; ]</td>
        </tr>
        <tr>
          <td style="font-weight: 700; text-align: center;">c)</td>
          <td>Giá trị cực tiểu của hàm số đã cho bằng <math><mo>−</mo><mn>24</mn></math>.</td>
          <td style="text-align: center;">[ &nbsp; ]</td>
          <td style="text-align: center;">[ &nbsp; ]</td>
        </tr>
        <tr>
          <td style="font-weight: 700; text-align: center;">d)</td>
          <td>Giá trị lớn nhất của hàm số <math><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo></math> trên đoạn <math><mo>[</mo><mo>−</mo><mn>3</mn><mo>;</mo><mn>3</mn><mo>]</mo></math> bằng <math><mn>8</mn></math>.</td>
          <td style="text-align: center;">[ &nbsp; ]</td>
          <td style="text-align: center;">[ &nbsp; ]</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- CÂU 10: TỰ LUẬN VIẾT TAY (TEST OCR HANDWRITTEN) -->
  <div class="question-item">
    <div class="question-title">
      <span class="question-badge">Câu 10</span>
      <span class="question-tag">Tự luận giải toán</span>
      <span class="question-tag">Thực nghiệm OCR chữ viết tay</span>
      Trong không gian <math><mi>O</mi><mi>x</mi><mi>y</mi><mi>z</mi></math>, 
      cho điểm <math><mi>A</mi><mo>(</mo><mn>1</mn><mo>;</mo><mn>2</mn><mo>;</mo><mo>−</mo><mn>1</mn><mo>)</mo></math> 
      và mặt phẳng <math><mo>(</mo><mi>P</mi><mo>)</mo><mo>:</mo><mn>2</mn><mi>x</mi><mo>−</mo><mn>2</mn><mi>y</mi><mo>+</mo><mi>z</mi><mo>+</mo><mn>5</mn><mo>=</mo><mn>0</mn></math>. 
      Hãy trình bày các bước tính khoảng cách từ điểm <math><mi>A</mi></math> đến mặt phẳng <math><mo>(</mo><mi>P</mi><mo>)</mo></math>.
    </div>

    <div class="handwriting-box">
      <div class="handwriting-label">✍ KHUNG LÀM BÀI VIẾT TAY (Dành cho học sinh làm bài / Chụp ảnh kiểm thử OCR):</div>
      <div class="dotted-line"></div>
      <div class="dotted-line"></div>
      <div class="dotted-line"></div>
      <div class="dotted-line"></div>
      <div class="dotted-line"></div>
      <div class="dotted-line"></div>
    </div>
  </div>

  <div class="page-num">Trang 2 / 4</div>
  <div class="page-break"></div>

  <!-- =======================================================================
       TRANG 3: BẢNG ĐÁP ÁN NHANH VÀ LỜI GIẢI CÂU 1 -> CÂU 5
       ======================================================================= -->
  <div class="section-banner-sol">
    PHẦN II: BẢNG ĐÁP ÁN VÀ LỜI GIẢI CHI TIẾT (GROUND TRUTH ĐỐI SOÁT OCR)
  </div>

  <table class="ans-matrix-table">
    <thead>
      <tr>
        <th>Câu</th>
        <th>1</th>
        <th>2</th>
        <th>3</th>
        <th>4</th>
        <th>5</th>
        <th>6</th>
        <th>7</th>
        <th>8</th>
        <th>9</th>
        <th>10</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="background: #f1f5f9; font-weight: 700;">Đ.Án</td>
        <td>C</td>
        <td>A</td>
        <td>B</td>
        <td>B</td>
        <td>C</td>
        <td>B</td>
        <td>A</td>
        <td>A</td>
        <td style="font-size: 11px;">Đ - Đ - Đ - Đ</td>
        <td><math><mfrac><mn>2</mn><mn>3</mn></mfrac></math></td>
      </tr>
    </tbody>
  </table>

  <!-- Lời giải 1 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 1 (Tiệm cận đứng)</span>
      <span class="solution-correct-ans">Đáp án: C (x = -2)</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Hàm số xác định trên tập <math><mi>D</mi><mo>=</mo><mi>ℝ</mi><mo>∖</mo><mo>{</mo><mo>−</mo><mn>2</mn><mo>}</mo></math>.
      </div>
      <div class="solution-step">
        • Xét giới hạn một bên tại điểm bất định <math><mi>x</mi><mo>=</mo><mo>−</mo><mn>2</mn></math>:
        <math display="inline">
          <munder><mo>lim</mo><mrow><mi>x</mi><mo>→</mo><msup><mrow><mo>(</mo><mo>−</mo><mn>2</mn><mo>)</mo></mrow><mo>+</mo></msup></mrow></munder><mfrac><mrow><mn>2</mn><mi>x</mi><mo>−</mo><mn>1</mn></mrow><mrow><mi>x</mi><mo>+</mo><mn>2</mn></mrow></mfrac><mo>=</mo><mo>−</mo><mo>∞</mo>
        </math> 
        và 
        <math display="inline">
          <munder><mo>lim</mo><mrow><mi>x</mi><mo>→</mo><msup><mrow><mo>(</mo><mo>−</mo><mn>2</mn><mo>)</mo></mrow><mo>−</mo></msup></mrow></munder><mfrac><mrow><mn>2</mn><mi>x</mi><mo>−</mo><mn>1</mn></mrow><mrow><mi>x</mi><mo>+</mo><mn>2</mn></mrow></mfrac><mo>=</mo><mo>+</mo><mo>∞</mo>
        </math>.
      </div>
      <div class="solution-step">
        • Kết luận: Đường thẳng <math><mi>x</mi><mo>=</mo><mo>−</mo><mn>2</mn></math> là tiệm cận đứng của đồ thị hàm số.
      </div>
    </div>
  </div>

  <!-- Lời giải 2 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 2 (Điểm cực đại)</span>
      <span class="solution-correct-ans">Đáp án: A (0; 2)</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Tập xác định: <math><mi>D</mi><mo>=</mo><mi>ℝ</mi></math>. Đạo hàm: 
        <math><msup><mi>f</mi><mo>′</mo></msup><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mn>3</mn><msup><mi>x</mi><mn>2</mn></msup><mo>−</mo><mn>6</mn><mi>x</mi><mo>=</mo><mn>3</mn><mi>x</mi><mo>(</mo><mi>x</mi><mo>−</mo><mn>2</mn><mo>)</mo></math>.
      </div>
      <div class="solution-step">
        • Cho <math><msup><mi>f</mi><mo>′</mo></msup><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mn>0</mn><mo>⇔</mo><mi>x</mi><mo>=</mo><mn>0</mn></math> hoặc <math><mi>x</mi><mo>=</mo><mn>2</mn></math>.
      </div>
      <div class="solution-step">
        • Bảng xét dấu: <math><msup><mi>f</mi><mo>′</mo></msup><mo>(</mo><mi>x</mi><mo>)</mo></math> đổi dấu từ dương sang âm khi qua <math><mi>x</mi><mo>=</mo><mn>0</mn></math>, do đó hàm số đạt cực đại tại <math><mi>x</mi><mo>=</mo><mn>0</mn></math> với giá trị cực đại <math><mi>f</mi><mo>(</mo><mn>0</mn><mo>)</mo><mo>=</mo><mn>2</mn></math>.
      </div>
      <div class="solution-step">
        • Tọa độ điểm cực đại của đồ thị hàm số là <math><mo>(</mo><mn>0</mn><mo>;</mo><mn>2</mn><mo>)</mo></math>.
      </div>
    </div>
  </div>

  <!-- Lời giải 3 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 3 (Phương trình mũ)</span>
      <span class="solution-correct-ans">Đáp án: B (x = 3)</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Biến đổi về cùng cơ số 2: <math><mn>32</mn><mo>=</mo><msup><mn>2</mn><mn>5</mn></msup></math>.
      </div>
      <div class="solution-step">
        • Phương trình trở thành: 
        <math><msup><mn>2</mn><mrow><mn>2</mn><mi>x</mi><mo>−</mo><mn>1</mn></mrow></msup><mo>=</mo><msup><mn>2</mn><mn>5</mn></msup><mo>⇔</mo><mn>2</mn><mi>x</mi><mo>−</mo><mn>1</mn><mo>=</mo><mn>5</mn><mo>⇔</mo><mn>2</mn><mi>x</mi><mo>=</mo><mn>6</mn><mo>⇔</mo><mi>x</mi><mo>=</mo><mn>3</mn></math>.
      </div>
    </div>
  </div>

  <!-- Lời giải 4 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 4 (Tích vô hướng vectơ Oxyz)</span>
      <span class="solution-correct-ans">Đáp án: B (8)</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Áp dụng công thức: 
        <math><mover><mi>a</mi><mo>→</mo></mover><mo>⋅</mo><mover><mi>b</mi><mo>→</mo></mover><mo>=</mo><msub><mi>a</mi><mi>x</mi></msub><msub><mi>b</mi><mi>x</mi></msub><mo>+</mo><msub><mi>a</mi><mi>y</mi></msub><msub><mi>b</mi><mi>y</mi></msub><mo>+</mo><msub><mi>a</mi><mi>z</mi></msub><msub><mi>b</mi><mi>z</mi></msub></math>.
      </div>
      <div class="solution-step">
        • Thay số: 
        <math><mover><mi>a</mi><mo>→</mo></mover><mo>⋅</mo><mover><mi>b</mi><mo>→</mo></mover><mo>=</mo><mn>1</mn><mo>⋅</mo><mn>2</mn><mo>+</mo><mo>(</mo><mo>−</mo><mn>2</mn><mo>)</mo><mo>⋅</mo><mo>(</mo><mo>−</mo><mn>4</mn><mo>)</mo><mo>+</mo><mo>(</mo><mo>−</mo><mn>1</mn><mo>)</mo><mo>⋅</mo><mn>2</mn><mo>=</mo><mn>2</mn><mo>+</mo><mn>8</mn><mo>−</mo><mn>2</mn><mo>=</mo><mn>8</mn></math>.
      </div>
    </div>
  </div>

  <!-- Lời giải 5 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 5 (Diện tích hình phẳng)</span>
      <span class="solution-correct-ans">Đáp án: C (64/3)</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Hoành độ giao điểm: 
        <math><msup><mi>x</mi><mn>2</mn></msup><mo>=</mo><mn>8</mn><mo>−</mo><msup><mi>x</mi><mn>2</mn></msup><mo>⇔</mo><mn>2</mn><msup><mi>x</mi><mn>2</mn></msup><mo>=</mo><mn>8</mn><mo>⇔</mo><msup><mi>x</mi><mn>2</mn></msup><mo>=</mo><mn>4</mn><mo>⇔</mo><mi>x</mi><mo>=</mo><mo>±</mo><mn>2</mn></math>.
      </div>
      <div class="solution-step">
        • Diện tích: 
        <math><mi>S</mi><mo>=</mo><msubsup><mo>∫</mo><mrow><mo>−</mo><mn>2</mn></mrow><mn>2</mn></msubsup><mrow><mo>(</mo><mn>8</mn><mo>−</mo><mn>2</mn><msup><mi>x</mi><mn>2</mn></msup><mo>)</mo></mrow><mi>d</mi><mi>x</mi><mo>=</mo><msubsup><mrow><mo>[</mo><mn>8</mn><mi>x</mi><mo>−</mo><mfrac><mrow><mn>2</mn><msup><mi>x</mi><mn>3</mn></msup></mrow><mn>3</mn></mfrac><mo>]</mo></mrow><mrow><mo>−</mo><mn>2</mn></mrow><mn>2</mn></msubsup><mo>=</mo><mfrac><mn>32</mn><mn>3</mn></mfrac><mo>−</mo><mrow><mo>(</mo><mo>−</mo><mfrac><mn>32</mn><mn>3</mn></mfrac><mo>)</mo></mrow><mo>=</mo><mfrac><mn>64</mn><mn>3</mn></mfrac></math>.
      </div>
    </div>
  </div>

  <div class="page-num">Trang 3 / 4</div>
  <div class="page-break"></div>

  <!-- =======================================================================
       TRANG 4: LỜI GIẢI CÂU 6 -> CÂU 10
       ======================================================================= -->
  <!-- Lời giải 6 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 6 (Nguyên hàm cơ bản)</span>
      <span class="solution-correct-ans">Đáp án: B (e^x - x^2 + C)</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Áp dụng công thức nguyên hàm cơ bản: 
        <math><mo>∫</mo><mrow><mo>(</mo><msup><mi>e</mi><mi>x</mi></msup><mo>−</mo><mn>2</mn><mi>x</mi><mo>)</mo></mrow><mi>d</mi><mi>x</mi><mo>=</mo><mo>∫</mo><msup><mi>e</mi><mi>x</mi></msup><mi>d</mi><mi>x</mi><mo>−</mo><mn>2</mn><mo>∫</mo><mi>x</mi><mi>d</mi><mi>x</mi><mo>=</mo><msup><mi>e</mi><mi>x</mi></msup><mo>−</mo><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo><mi>C</mi></math>.
      </div>
    </div>
  </div>

  <!-- Lời giải 7 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 7 (Phương trình mặt phẳng)</span>
      <span class="solution-correct-ans">Đáp án: A (2x + y - z + 3 = 0)</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Phương trình mặt phẳng: 
        <math><mn>2</mn><mo>(</mo><mi>x</mi><mo>−</mo><mn>1</mn><mo>)</mo><mo>+</mo><mn>1</mn><mo>(</mo><mi>y</mi><mo>+</mo><mn>2</mn><mo>)</mo><mo>−</mo><mn>1</mn><mo>(</mo><mi>z</mi><mo>−</mo><mn>3</mn><mo>)</mo><mo>=</mo><mn>0</mn></math>.
      </div>
      <div class="solution-step">
        • Khai triển rút gọn: 
        <math><mn>2</mn><mi>x</mi><mo>−</mo><mn>2</mn><mo>+</mo><mi>y</mi><mo>+</mo><mn>2</mn><mo>−</mo><mi>z</mi><mo>+</mo><mn>3</mn><mo>=</mo><mn>0</mn><mo>⇔</mo><mn>2</mn><mi>x</mi><mo>+</mo><mi>y</mi><mo>−</mo><mi>z</mi><mo>+</mo><mn>3</mn><mo>=</mo><mn>0</mn></math>.
      </div>
    </div>
  </div>

  <!-- Lời giải 8 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 8 (Xác suất có điều kiện)</span>
      <span class="solution-correct-ans">Đáp án: A (4/9)</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Gọi <math><mi>A</mi></math> là biến cố "Bóng thứ nhất màu trắng", <math><mi>B</mi></math> là biến cố "Bóng thứ hai màu đỏ".
      </div>
      <div class="solution-step">
        • Khi quả bóng thứ nhất màu trắng đã lấy ra (không hoàn lại), hộp còn lại 9 quả bóng (gồm 5 bóng trắng và 4 bóng đỏ).
      </div>
      <div class="solution-step">
        • Xác suất có điều kiện: 
        <math><mi>P</mi><mo>(</mo><mi>B</mi><mo>|</mo><mi>A</mi><mo>)</mo><mo>=</mo><mfrac><mn>4</mn><mn>9</mn></mfrac></math>.
      </div>
    </div>
  </div>

  <!-- Lời giải 9 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 9 (Đúng/Sai khảo sát hàm số)</span>
      <span class="solution-correct-ans">Đáp án: a-Đ, b-Đ, c-Đ, d-Đ</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • <strong>Ý a) ĐÚNG</strong>: <math><msup><mi>f</mi><mo>′</mo></msup><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mn>3</mn><msup><mi>x</mi><mn>2</mn></msup><mo>−</mo><mn>12</mn></math>.
      </div>
      <div class="solution-step">
        • <strong>Ý b) ĐÚNG</strong>: <math><msup><mi>f</mi><mo>′</mo></msup><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mn>0</mn><mo>⇔</mo><mn>3</mn><msup><mi>x</mi><mn>2</mn></msup><mo>−</mo><mn>12</mn><mo>=</mo><mn>0</mn><mo>⇔</mo><mi>x</mi><mo>=</mo><mo>±</mo><mn>2</mn></math>. Tập nghiệm <math><mi>S</mi><mo>=</mo><mo>{</mo><mo>−</mo><mn>2</mn><mo>;</mo><mn>2</mn><mo>}</mo></math>.
      </div>
      <div class="solution-step">
        • <strong>Ý c) ĐÚNG</strong>: Điểm cực tiểu <math><mi>x</mi><mo>=</mo><mn>2</mn></math>, giá trị cực tiểu: 
        <math><mi>f</mi><mo>(</mo><mn>2</mn><mo>)</mo><mo>=</mo><msup><mn>2</mn><mn>3</mn></msup><mo>−</mo><mn>12</mn><mo>(</mo><mn>2</mn><mo>)</mo><mo>−</mo><mn>8</mn><mo>=</mo><mo>−</mo><mn>24</mn></math>.
      </div>
      <div class="solution-step">
        • <strong>Ý d) ĐÚNG</strong>: Trên <math><mo>[</mo><mo>−</mo><mn>3</mn><mo>;</mo><mn>3</mn><mo>]</mo></math>, có <math><mi>f</mi><mo>(</mo><mo>−</mo><mn>3</mn><mo>)</mo><mo>=</mo><mn>1</mn></math>; <math><mi>f</mi><mo>(</mo><mo>−</mo><mn>2</mn><mo>)</mo><mo>=</mo><mn>8</mn></math>; <math><mi>f</mi><mo>(</mo><mn>2</mn><mo>)</mo><mo>=</mo><mo>−</mo><mn>24</mn></math>; <math><mi>f</mi><mo>(</mo><mn>3</mn><mo>)</mo><mo>=</mo><mo>−</mo><mn>17</mn></math>. 
        Vậy <math><munder><mo>max</mo><mrow><mo>[</mo><mo>−</mo><mn>3</mn><mo>;</mo><mn>3</mn><mo>]</mo></mrow></munder><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mi>f</mi><mo>(</mo><mo>−</mo><mn>2</mn><mo>)</mo><mo>=</mo><mn>8</mn></math>.
      </div>
    </div>
  </div>

  <!-- Lời giải 10 -->
  <div class="solution-item">
    <div class="solution-header">
      <span style="font-weight: 700; color: #0f172a;">Lời giải Câu 10 (Khoảng cách điểm đến mặt phẳng - Tự luận)</span>
      <span class="solution-correct-ans">Đáp án: d = 2/3</span>
    </div>
    <div class="solution-body">
      <div class="solution-step">
        • Công thức: 
        <math><mi>d</mi><mrow><mo>(</mo><mi>A</mi><mo>,</mo><mo>(</mo><mi>P</mi><mo>)</mo><mo>)</mo></mrow><mo>=</mo><mfrac><mrow><mo>|</mo><mi>A</mi><msub><mi>x</mi><mn>0</mn></msub><mo>+</mo><mi>B</mi><msub><mi>y</mi><mn>0</mn></msub><mo>+</mo><mi>C</mi><msub><mi>z</mi><mn>0</mn></msub><mo>+</mo><mi>D</mi><mo>|</mo></mrow><msqrt><msup><mi>A</mi><mn>2</mn></msup><mo>+</mo><msup><mi>B</mi><mn>2</mn></msup><mo>+</mo><msup><mi>C</mi><mn>2</mn></msup></msqrt></mfrac></math>.
      </div>
      <div class="solution-step">
        • Thay tọa độ <math><mi>A</mi><mo>(</mo><mn>1</mn><mo>;</mo><mn>2</mn><mo>;</mo><mo>−</mo><mn>1</mn><mo>)</mo></math> và phương trình <math><mo>(</mo><mi>P</mi><mo>)</mo><mo>:</mo><mn>2</mn><mi>x</mi><mo>−</mo><mn>2</mn><mi>y</mi><mo>+</mo><mi>z</mi><mo>+</mo><mn>5</mn><mo>=</mo><mn>0</mn></math>:
        <math display="block">
          <mi>d</mi><mrow><mo>(</mo><mi>A</mi><mo>,</mo><mo>(</mo><mi>P</mi><mo>)</mo><mo>)</mo></mrow>
          <mo>=</mo><mfrac><mrow><mo>|</mo><mn>2</mn><mo>(</mo><mn>1</mn><mo>)</mo><mo>−</mo><mn>2</mn><mo>(</mo><mn>2</mn><mo>)</mo><mo>+</mo><mn>1</mn><mo>(</mo><mo>−</mo><mn>1</mn><mo>)</mo><mo>+</mo><mn>5</mn><mo>|</mo></mrow><msqrt><msup><mn>2</mn><mn>2</mn></msup><mo>+</mo><msup><mrow><mo>(</mo><mo>−</mo><mn>2</mn><mo>)</mo></mrow><mn>2</mn></msup><mo>+</mo><msup><mn>1</mn><mn>2</mn></msup></msqrt></mfrac>
          <mo>=</mo><mfrac><mrow><mo>|</mo><mn>2</mn><mo>−</mo><mn>4</mn><mo>−</mo><mn>1</mn><mo>+</mo><mn>5</mn><mo>|</mo></mrow><msqrt><mn>4</mn><mo>+</mo><mn>4</mn><mo>+</mo><mn>1</mn></msqrt></mfrac>
          <mo>=</mo><mfrac><mrow><mo>|</mo><mn>2</mn><mo>|</mo></mrow><msqrt><mn>9</mn></msqrt></mfrac>
          <mo>=</mo><mfrac><mn>2</mn><mn>3</mn></mfrac>
        </math>
      </div>
    </div>
  </div>

  <div class="footer-note">
    © 2026 EduMS - Nền Tảng Khảo Thí &amp; Học Tập Thông Minh · Dữ liệu chuẩn hóa phục vụ kiểm thử mô hình OCR Toán học
  </div>
  <div class="page-num">Trang 4 / 4</div>

</body>
</html>
"""

def generate_pdf():
    print(f"Writing HTML to: {HTML_PATH}")
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)

    chrome_cmd = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        str(HTML_PATH),
    ]

    print("Running Chrome headless with --no-pdf-header-footer to generate PDF...")
    result = subprocess.run(chrome_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"PDF generated successfully at: {PDF_PATH}")
        if PDF_PATH.exists():
            size = os.path.getsize(PDF_PATH)
            print(f"File size: {size:,} bytes")
            
            # Verify page count
            doc = fitz.open(str(PDF_PATH))
            print(f"Verified total pages in PDF: {len(doc)}")
    else:
        print(f"Error generating PDF: {result.stderr}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    generate_pdf()
