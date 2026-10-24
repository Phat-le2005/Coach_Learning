"use client";

import type { ReactNode } from "react";

export function getMathChapterType(label: string, fallbackIndex = 0): number {
  const l = label.toLowerCase();
  if (l.includes("đạo hàm") || l.includes("khảo sát")) return 0;
  if (l.includes("mũ") || l.includes("logarit") || l.includes("lôgarit")) return 1;
  if (l.includes("vectơ") || l.includes("hệ tọa độ")) return 2;
  if (l.includes("đặc trưng") || l.includes("mẫu số liệu") || l.includes("thống kê") || l.includes("phân tán")) return 3;
  if (l.includes("nguyên hàm") || l.includes("tích phân")) return 4;
  if (l.includes("phương pháp tọa độ") || l.includes("mặt phẳng") || l.includes("mặt cầu")) return 5;
  if (l.includes("xác suất")) return 6;
  return fallbackIndex % 7;
}

export interface MathChapterIllustrationProps {
  type: number;
  index?: number;
  className?: string;
}

export function MathChapterIllustration({
  type,
  index = 0,
  className,
}: MathChapterIllustrationProps): ReactNode {
  switch (type) {
    case 0:
      // Ch 1: Calculus Cubic curve + Extrema + Tangent line
      return (
        <svg className={className} viewBox="0 0 260 95" fill="none">
          <defs>
            <linearGradient id={`mathCubicGrad-${index}`} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.4" />
              <stop offset="45%" stopColor="#10b981" />
              <stop offset="100%" stopColor="#06b6d4" />
            </linearGradient>
          </defs>
          <line x1="20" y1="78" x2="245" y2="78" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.2" />
          <polyline points="240,75 246,78 240,81" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.2" fill="none" />
          <line x1="45" y1="88" x2="45" y2="10" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.2" />
          <polyline points="42,15 45,9 48,15" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.2" fill="none" />
          <text x="242" y="90" fontSize="9" fill="currentColor" fillOpacity="0.5" fontWeight="600">x</text>
          <text x="34" y="16" fontSize="9" fill="currentColor" fillOpacity="0.5" fontWeight="600">y</text>
          <text x="36" y="86" fontSize="8" fill="currentColor" fillOpacity="0.4">O</text>

          {/* Tangent line at local max */}
          <line x1="55" y1="28" x2="145" y2="28" stroke="#d97706" strokeOpacity="0.45" strokeDasharray="3 3" strokeWidth="1.2" />
          <text x="58" y="24" fontSize="8.5" fill="#d97706" fontWeight="700">y&apos; = 0</text>

          {/* Cubic curve */}
          <path
            d="M 38 75 C 65 65, 80 28, 100 28 C 120 28, 145 62, 165 62 C 185 62, 210 35, 232 14"
            stroke={`url(#mathCubicGrad-${index})`}
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          {/* Local max point */}
          <circle cx="100" cy="28" r="4.5" fill="#10b981" />
          <circle cx="100" cy="28" r="2.2" fill="#ffffff" />
          <text x="95" y="19" fontSize="8.5" fill="#047857" fontWeight="800">CĐ</text>

          {/* Local min point */}
          <circle cx="165" cy="62" r="4.5" fill="#06b6d4" />
          <circle cx="165" cy="62" r="2.2" fill="#ffffff" />
          <text x="161" y="74" fontSize="8.5" fill="#0891b2" fontWeight="800">CT</text>

          {/* Formula tag */}
          <rect x="180" y="74" width="62" height="15" rx="4" fill="rgba(16,185,129,0.12)" />
          <text x="211" y="85" textAnchor="middle" fontSize="9" fill="#065f46" fontWeight="700">y = f(x)</text>
        </svg>
      );

    case 1:
      // Ch 2: Exponential and Logarithmic Curves
      return (
        <svg className={className} viewBox="0 0 260 95" fill="none">
          <line x1="20" y1="72" x2="245" y2="72" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.2" />
          <polyline points="240,69 246,72 240,75" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.2" fill="none" />
          <line x1="85" y1="88" x2="85" y2="8" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.2" />
          <polyline points="82,13 85,7 88,13" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.2" fill="none" />
          <text x="242" y="84" fontSize="9" fill="currentColor" fillOpacity="0.5" fontWeight="600">x</text>
          <text x="74" y="14" fontSize="9" fill="currentColor" fillOpacity="0.5" fontWeight="600">y</text>

          {/* Diagonal y = x */}
          <line x1="35" y1="85" x2="210" y2="12" stroke="currentColor" strokeOpacity="0.2" strokeDasharray="3 3" strokeWidth="1" />
          <text x="202" y="24" fontSize="8" fill="currentColor" fillOpacity="0.45" fontStyle="italic">y = x</text>

          {/* y = a^x */}
          <path
            d="M 25 71 C 55 70, 75 62, 85 48 C 95 34, 125 18, 145 10"
            stroke="#38bdf8"
            strokeWidth="2.4"
            strokeLinecap="round"
          />
          <circle cx="85" cy="48" r="3.5" fill="#38bdf8" />
          <circle cx="85" cy="48" r="1.8" fill="#ffffff" />
          <text x="64" y="47" fontSize="8" fill="#0284c7" fontWeight="700">(0;1)</text>
          <text x="132" y="22" fontSize="9" fill="#0369a1" fontWeight="800">y = aˣ</text>

          {/* y = log_a(x) */}
          <path
            d="M 91 85 C 93 78, 105 74, 122 72 C 155 68, 195 55, 235 46"
            stroke="#0284c7"
            strokeWidth="2.4"
            strokeLinecap="round"
          />
          <circle cx="122" cy="72" r="3.5" fill="#0284c7" />
          <circle cx="122" cy="72" r="1.8" fill="#ffffff" />
          <text x="117" y="84" fontSize="8" fill="#0369a1" fontWeight="700">(1;0)</text>
          <text x="188" y="42" fontSize="9" fill="#0284c7" fontWeight="800">y = logₐx</text>
        </svg>
      );

    case 2:
      // Ch 3: 3D Isometric Oxyz + Basis Vectors + Vector u = OM
      return (
        <svg className={className} viewBox="0 0 260 95" fill="none">
          <line x1="110" y1="68" x2="110" y2="12" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.4" />
          <polyline points="107,17 110,11 113,17" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" fill="none" />
          <text x="102" y="14" fontSize="9.5" fill="currentColor" fillOpacity="0.7" fontWeight="700">z</text>

          <line x1="110" y1="68" x2="42" y2="88" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.4" />
          <polyline points="47,84 40,88 48,91" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" fill="none" />
          <text x="32" y="90" fontSize="9.5" fill="currentColor" fillOpacity="0.7" fontWeight="700">x</text>

          <line x1="110" y1="68" x2="235" y2="68" stroke="currentColor" strokeOpacity="0.4" strokeWidth="1.4" />
          <polyline points="230,65 236,68 230,71" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4" fill="none" />
          <text x="240" y="72" fontSize="9.5" fill="currentColor" fillOpacity="0.7" fontWeight="700">y</text>
          <text x="100" y="78" fontSize="8.5" fill="currentColor" fillOpacity="0.5">O</text>

          {/* Basis vectors */}
          <line x1="110" y1="68" x2="88" y2="74" stroke="#8578cf" strokeWidth="2" strokeLinecap="round" />
          <text x="82" y="71" fontSize="8" fill="#6d28d9" fontWeight="700">i⃗</text>
          <line x1="110" y1="68" x2="145" y2="68" stroke="#8578cf" strokeWidth="2" strokeLinecap="round" />
          <text x="142" y="63" fontSize="8" fill="#6d28d9" fontWeight="700">j⃗</text>
          <line x1="110" y1="68" x2="110" y2="44" stroke="#8578cf" strokeWidth="2" strokeLinecap="round" />
          <text x="115" y="47" fontSize="8" fill="#6d28d9" fontWeight="700">k⃗</text>

          {/* 3D projection box to M */}
          <line x1="110" y1="68" x2="140" y2="76" stroke="currentColor" strokeOpacity="0.25" strokeDasharray="2 2" strokeWidth="1" />
          <line x1="140" y1="76" x2="175" y2="52" stroke="currentColor" strokeOpacity="0.25" strokeDasharray="2 2" strokeWidth="1" />
          <line x1="175" y1="52" x2="175" y2="28" stroke="currentColor" strokeOpacity="0.25" strokeDasharray="2 2" strokeWidth="1" />
          <line x1="110" y1="44" x2="175" y2="28" stroke="currentColor" strokeOpacity="0.2" strokeDasharray="2 2" strokeWidth="1" />

          {/* Vector OM */}
          <line x1="110" y1="68" x2="173" y2="29" stroke="#7c3aed" strokeWidth="2.4" strokeLinecap="round" />
          <polygon points="175,28 168,34 169,30" fill="#7c3aed" />

          <circle cx="175" cy="28" r="4" fill="#7c3aed" />
          <circle cx="175" cy="28" r="1.8" fill="#ffffff" />
          <text x="182" y="27" fontSize="9" fill="#5b21b6" fontWeight="800">M(x;y;z)</text>
          <text x="135" y="42" fontSize="8.5" fill="#6d28d9" fontWeight="700">u⃗ = OM⃗</text>
        </svg>
      );

    case 3:
      // Ch 4: Statistics Grouped Data Histogram + Bell Curve
      return (
        <svg className={className} viewBox="0 0 260 95" fill="none">
          <line x1="20" y1="80" x2="245" y2="80" stroke="currentColor" strokeOpacity="0.25" strokeWidth="1.2" />
          <polyline points="240,77 246,80 240,83" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.2" fill="none" />
          <line x1="30" y1="88" x2="30" y2="15" stroke="currentColor" strokeOpacity="0.25" strokeWidth="1.2" />
          <polyline points="27,20 30,14 33,20" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.2" fill="none" />
          <text x="242" y="90" fontSize="8.5" fill="currentColor" fillOpacity="0.5">mức</text>
          <text x="22" y="16" fontSize="8.5" fill="currentColor" fillOpacity="0.5">ni</text>

          {/* Histogram bars */}
          <rect x="42" y="65" width="26" height="15" rx="3" fill="rgba(217, 119, 6, 0.22)" stroke="#d97706" strokeWidth="1.2" />
          <rect x="72" y="45" width="26" height="35" rx="3" fill="rgba(217, 119, 6, 0.35)" stroke="#d97706" strokeWidth="1.2" />
          <rect x="102" y="25" width="26" height="55" rx="3" fill="rgba(217, 119, 6, 0.55)" stroke="#d97706" strokeWidth="1.4" />
          <rect x="132" y="38" width="26" height="42" rx="3" fill="rgba(217, 119, 6, 0.4)" stroke="#d97706" strokeWidth="1.2" />
          <rect x="162" y="58" width="26" height="22" rx="3" fill="rgba(217, 119, 6, 0.25)" stroke="#d97706" strokeWidth="1.2" />
          <rect x="192" y="70" width="26" height="10" rx="3" fill="rgba(217, 119, 6, 0.15)" stroke="#d97706" strokeWidth="1" />

          {/* Normal distribution bell curve */}
          <path
            d="M 35 78 C 65 77, 85 60, 105 24 C 115 16, 125 16, 135 24 C 155 60, 175 77, 225 78"
            stroke="#b45309"
            strokeWidth="2.2"
            strokeLinecap="round"
          />

          {/* Median Q2 line */}
          <line x1="115" y1="18" x2="115" y2="80" stroke="#b45309" strokeDasharray="3 3" strokeWidth="1.4" />
          <circle cx="115" cy="18" r="3.5" fill="#b45309" />
          <circle cx="115" cy="18" r="1.5" fill="#fff" />
          <text x="110" y="12" fontSize="9" fill="#92400e" fontWeight="800">Q₂ (Me)</text>

          {/* Formula tag */}
          <rect x="180" y="20" width="65" height="16" rx="4" fill="rgba(217,119,6,0.18)" />
          <text x="212" y="32" textAnchor="middle" fontSize="9" fill="#78350f" fontWeight="700">s² ; s = √s²</text>
        </svg>
      );

    case 4:
      // Ch 5: Antiderivatives & Integrals
      return (
        <svg className={className} viewBox="0 0 260 95" fill="none">
          <defs>
            <linearGradient id={`mathIntegralArea-${index}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#e11d48" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#e11d48" stopOpacity="0.08" />
            </linearGradient>
          </defs>

          <line x1="20" y1="75" x2="245" y2="75" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.2" />
          <polyline points="240,72 246,75 240,78" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.2" fill="none" />
          <line x1="45" y1="88" x2="45" y2="10" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.2" />
          <polyline points="42,15 45,9 48,15" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.2" fill="none" />
          <text x="242" y="87" fontSize="8.5" fill="currentColor" fillOpacity="0.5">x</text>
          <text x="35" y="15" fontSize="8.5" fill="currentColor" fillOpacity="0.5">y</text>

          {/* Shaded Area */}
          <path
            d="M 85 75 L 85 45 C 105 32, 130 25, 150 35 C 165 42, 172 48, 180 52 L 180 75 Z"
            fill={`url(#mathIntegralArea-${index})`}
          />

          {/* Curve */}
          <path
            d="M 55 60 C 75 52, 105 32, 130 25 C 155 18, 175 48, 220 56"
            stroke="#e11d48"
            strokeWidth="2.4"
            strokeLinecap="round"
          />

          <line x1="85" y1="45" x2="85" y2="75" stroke="#9f1239" strokeDasharray="3 3" strokeWidth="1.2" />
          <line x1="180" y1="52" x2="180" y2="75" stroke="#9f1239" strokeDasharray="3 3" strokeWidth="1.2" />
          <circle cx="85" cy="75" r="2.5" fill="#9f1239" />
          <circle cx="180" cy="75" r="2.5" fill="#9f1239" />
          <text x="82" y="86" fontSize="9" fill="#9f1239" fontWeight="800">a</text>
          <text x="177" y="86" fontSize="9" fill="#9f1239" fontWeight="800">b</text>

          <text x="130" y="58" fontSize="12" fill="#9f1239" fontWeight="800" fontStyle="italic">S</text>

          <rect x="155" y="14" width="90" height="20" rx="5" fill="rgba(225, 29, 72, 0.15)" stroke="rgba(225, 29, 72, 0.35)" strokeWidth="1" />
          <text x="200" y="28" textAnchor="middle" fontSize="10" fill="#9f1239" fontWeight="800">S = ∫ₐᵇ f(x)dx</text>
        </svg>
      );

    case 5:
      // Ch 6: 3D Plane (alpha) with normal vector n and line d
      return (
        <svg className={className} viewBox="0 0 260 95" fill="none">
          <defs>
            <linearGradient id={`mathPlaneGrad-${index}`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#0d9488" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#0d9488" stopOpacity="0.08" />
            </linearGradient>
          </defs>

          <polygon
            points="50,75 185,75 225,38 90,38"
            fill={`url(#mathPlaneGrad-${index})`}
            stroke="#0d9488"
            strokeWidth="1.6"
          />
          <text x="65" y="70" fontSize="10" fill="#0f766e" fontWeight="800">(α)</text>

          <line x1="135" y1="56" x2="135" y2="12" stroke="#0d9488" strokeWidth="2.4" strokeLinecap="round" />
          <polygon points="135,10 131,18 139,18" fill="#0d9488" />
          <polyline points="135,46 143,46 143,54" stroke="#0d9488" strokeWidth="1.2" fill="none" />
          <text x="144" y="22" fontSize="9.5" fill="#0f766e" fontWeight="800">n⃗ = (A;B;C)</text>

          <line x1="75" y1="14" x2="105" y2="48" stroke="#d97706" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="105" y1="48" x2="125" y2="72" stroke="#d97706" strokeWidth="1.8" strokeDasharray="3 3" />
          <line x1="125" y1="72" x2="140" y2="90" stroke="#d97706" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="105" cy="48" r="3" fill="#d97706" />
          <text x="60" y="20" fontSize="9" fill="#d97706" fontWeight="700">d</text>
          <text x="96" y="44" fontSize="8" fill="#b45309" fontWeight="700">I</text>

          <rect x="155" y="72" width="95" height="16" rx="4" fill="rgba(13,148,136,0.18)" />
          <text x="202" y="83" textAnchor="middle" fontSize="8" fill="#115e59" fontWeight="700">Ax + By + Cz + D = 0</text>
        </svg>
      );

    case 6:
    default:
      // Ch 7: Probability Tree Diagram
      return (
        <svg className={className} viewBox="0 0 260 95" fill="none">
          <circle cx="28" cy="48" r="4.5" fill="#059669" />
          <circle cx="28" cy="48" r="2" fill="#fff" />
          <text x="16" y="52" fontSize="8.5" fill="currentColor" fillOpacity="0.6" fontWeight="700">Ω</text>

          <line x1="32" y1="46" x2="90" y2="28" stroke="#059669" strokeWidth="1.6" />
          <text x="50" y="32" fontSize="8" fill="#047857" fontWeight="700">P(A)</text>
          <circle cx="90" cy="28" r="4" fill="#059669" />
          <text x="96" y="24" fontSize="9" fill="#065f46" fontWeight="800">A</text>

          <line x1="32" y1="50" x2="90" y2="68" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.4" />
          <text x="48" y="67" fontSize="8" fill="currentColor" fillOpacity="0.5">P(Ā)</text>
          <circle cx="90" cy="68" r="3.5" fill="currentColor" fillOpacity="0.4" />
          <text x="96" y="72" fontSize="9" fill="currentColor" fillOpacity="0.6" fontWeight="800">Ā</text>

          <line x1="94" y1="26" x2="160" y2="16" stroke="#059669" strokeWidth="1.4" />
          <text x="115" y="16" fontSize="7.5" fill="#047857" fontWeight="600">P(B|A)</text>
          <circle cx="160" cy="16" r="3" fill="#059669" />
          <text x="166" y="19" fontSize="8.5" fill="#065f46" fontWeight="800">B</text>

          <line x1="94" y1="30" x2="160" y2="40" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.2" />
          <text x="115" y="41" fontSize="7.5" fill="currentColor" fillOpacity="0.5">P(B̄|A)</text>
          <circle cx="160" cy="40" r="3" fill="currentColor" fillOpacity="0.4" />
          <text x="166" y="43" fontSize="8.5" fill="currentColor" fillOpacity="0.6">B̄</text>

          <rect x="180" y="48" width="75" height="36" rx="6" fill="rgba(5,150,105,0.12)" stroke="rgba(5,150,105,0.3)" strokeWidth="1" />
          <text x="217" y="62" textAnchor="middle" fontSize="7.5" fill="#065f46" fontWeight="700">P(A ∩ B) =</text>
          <text x="217" y="76" textAnchor="middle" fontSize="8" fill="#047857" fontWeight="800">P(A) · P(B|A)</text>
        </svg>
      );
  }
}
