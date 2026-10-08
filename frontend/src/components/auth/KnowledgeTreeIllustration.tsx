import styles from "./knowledge-tree.module.css";

export function KnowledgeTreeIllustration() {
  return (
    <div className={styles.treeContainer} aria-hidden="true">
      <svg
        className={styles.treeSvg}
        viewBox="0 0 540 440"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          {/* Sunbeams */}
          <linearGradient id="tree-sunray-1" x1="60" y1="0" x2="320" y2="440" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#fff8da" stopOpacity="0.45" />
            <stop offset="40%" stopColor="#dcefe5" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#286955" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="tree-sunray-2" x1="140" y1="0" x2="440" y2="440" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#fff8da" stopOpacity="0.35" />
            <stop offset="50%" stopColor="#c3edd5" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#173f34" stopOpacity="0" />
          </linearGradient>

          {/* Trunk & Bark */}
          <linearGradient id="trunk-grad" x1="270" y1="180" x2="270" y2="430" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#28503e" />
            <stop offset="40%" stopColor="#1b382c" />
            <stop offset="100%" stopColor="#12271f" />
          </linearGradient>
          <linearGradient id="bark-highlight" x1="240" y1="200" x2="300" y2="410" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#41735c" />
            <stop offset="100%" stopColor="#1c3a2e" />
          </linearGradient>

          {/* Earth / Roots mound */}
          <linearGradient id="earth-mound" x1="270" y1="380" x2="270" y2="440" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#1c4434" />
            <stop offset="100%" stopColor="#0d241c" />
          </linearGradient>

          {/* Foliage Canopy Layers */}
          {/* Back foliage (deep shadow) */}
          <linearGradient id="canopy-back-grad" x1="270" y1="50" x2="270" y2="300" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#164333" />
            <stop offset="100%" stopColor="#0d291f" />
          </linearGradient>

          {/* Mid foliage (rich forest green) */}
          <linearGradient id="canopy-mid-grad" x1="270" y1="40" x2="270" y2="280" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#2c7256" />
            <stop offset="50%" stopColor="#205344" />
            <stop offset="100%" stopColor="#173f34" />
          </linearGradient>

          {/* Front foliage (vibrant emerald) */}
          <linearGradient id="canopy-front-grad" x1="270" y1="30" x2="270" y2="250" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#439474" />
            <stop offset="60%" stopColor="#2f755a" />
            <stop offset="100%" stopColor="#1e523f" />
          </linearGradient>

          {/* Highlight crowns (fresh mint) */}
          <linearGradient id="canopy-crown-grad" x1="270" y1="20" x2="270" y2="180" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#6fd4a5" />
            <stop offset="50%" stopColor="#4fa381" />
            <stop offset="100%" stopColor="#358564" />
          </linearGradient>

          {/* Glow filter */}
          <filter id="soft-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* 1. Sunbeams streaming through the canopy */}
        <g className={styles.sunray}>
          <polygon points="40,-20 180,-20 360,440 180,440" fill="url(#tree-sunray-1)" />
        </g>
        <g className={styles.sunraySecond}>
          <polygon points="120,-20 250,-20 480,440 330,440" fill="url(#tree-sunray-2)" />
        </g>

        {/* 2. Earth Mounds & Soil Mound */}
        <path
          d="M30 425 Q140 395 270 398 Q400 395 510 425 Q540 435 540 440 L0 440 Q0 435 30 425 Z"
          fill="url(#earth-mound)"
        />
        <ellipse cx="270" cy="415" rx="190" ry="16" fill="#122c22" opacity="0.6" />

        {/* 3. Deep Root System */}
        <g fill="url(#trunk-grad)">
          {/* Main central anchor roots */}
          <path d="M255 385 Q235 410 190 422 Q215 425 245 408 Q260 398 265 385 Z" />
          <path d="M275 385 Q295 410 345 423 Q320 426 295 408 Q280 398 275 385 Z" />
          {/* Left winding roots */}
          <path d="M245 375 Q210 395 150 415 Q175 418 225 400 Q240 390 245 375 Z" />
          <path d="M235 380 Q180 405 110 424 Q135 426 195 412 Q230 395 235 380 Z" />
          {/* Right winding roots */}
          <path d="M295 375 Q330 395 390 415 Q365 418 315 400 Q300 390 295 375 Z" />
          <path d="M305 380 Q360 405 430 424 Q405 426 345 412 Q310 395 305 380 Z" />
        </g>

        {/* 4. Grand Tree Trunk & Main Branches */}
        <g>
          {/* Base Trunk */}
          <path
            d="M238 385 C242 330 236 290 244 245 C248 220 235 190 215 170 C228 172 238 182 246 196 C255 180 262 165 270 148 C278 165 285 180 294 196 C302 182 312 172 325 170 C305 190 292 220 296 245 C304 290 298 330 302 385 Z"
            fill="url(#trunk-grad)"
          />

          {/* Left Primary Bough */}
          <path
            d="M244 245 C220 235 180 225 145 238 C170 232 205 240 230 258 Z"
            fill="url(#trunk-grad)"
          />
          <path
            d="M236 220 C200 200 160 185 118 192 C145 190 185 204 218 228 Z"
            fill="url(#trunk-grad)"
          />

          {/* Right Primary Bough */}
          <path
            d="M296 245 C320 235 360 225 395 238 C370 232 335 240 310 258 Z"
            fill="url(#trunk-grad)"
          />
          <path
            d="M304 220 C340 200 380 185 422 192 C395 190 355 204 322 228 Z"
            fill="url(#trunk-grad)"
          />

          {/* Trunk Bark Texture Lines */}
          <path d="M255 260 Q252 315 258 375" stroke="url(#bark-highlight)" strokeWidth="3" strokeLinecap="round" opacity="0.65" />
          <path d="M270 235 Q268 300 272 380" stroke="url(#bark-highlight)" strokeWidth="3.5" strokeLinecap="round" opacity="0.8" />
          <path d="M285 255 Q288 320 282 375" stroke="url(#bark-highlight)" strokeWidth="3" strokeLinecap="round" opacity="0.65" />
        </g>

        {/* 5. Canopy Foliage - Layer A (Back - Deep Shadows) */}
        <g fill="url(#canopy-back-grad)" opacity="0.95">
          <circle cx="160" cy="180" r="68" />
          <circle cx="380" cy="180" r="68" />
          <circle cx="210" cy="120" r="76" />
          <circle cx="330" cy="120" r="76" />
          <circle cx="270" cy="95" r="82" />
        </g>

        {/* 6. Canopy Foliage - Layer B (Mid - Forest Green) */}
        <g fill="url(#canopy-mid-grad)">
          {/* Left clusters */}
          <circle cx="130" cy="195" r="58" />
          <circle cx="185" cy="165" r="66" />
          <circle cx="155" cy="130" r="60" />
          {/* Right clusters */}
          <circle cx="410" cy="195" r="58" />
          <circle cx="355" cy="165" r="66" />
          <circle cx="385" cy="130" r="60" />
          {/* Center clusters */}
          <circle cx="230" cy="140" r="72" />
          <circle cx="310" cy="140" r="72" />
          <circle cx="270" cy="115" r="78" />
        </g>

        {/* 7. Canopy Foliage - Layer C (Front - Vibrant Emerald) */}
        <g fill="url(#canopy-front-grad)">
          {/* Left lower & mid blooms */}
          <circle cx="150" cy="210" r="46" />
          <circle cx="205" cy="185" r="54" />
          <circle cx="170" cy="145" r="52" />
          {/* Right lower & mid blooms */}
          <circle cx="390" cy="210" r="46" />
          <circle cx="335" cy="185" r="54" />
          <circle cx="370" cy="145" r="52" />
          {/* Upper canopy center */}
          <circle cx="250" cy="100" r="64" />
          <circle cx="290" cy="100" r="64" />
          <circle cx="270" cy="72" r="66" />
        </g>

        {/* 8. Canopy Foliage - Layer D (Crown Highlights - Fresh Mint) */}
        <g fill="url(#canopy-crown-grad)">
          <circle cx="270" cy="55" r="48" />
          <circle cx="240" cy="80" r="42" />
          <circle cx="300" cy="80" r="42" />
          <circle cx="185" cy="120" r="38" />
          <circle cx="355" cy="120" r="38" />
          <circle cx="130" cy="170" r="34" />
          <circle cx="410" cy="170" r="34" />
        </g>

        {/* 9. Luminous Knowledge Buds / Concept Nodes */}
        {/* Node 1: Amber Bud (Gốc rễ vững chắc / Foundations) */}
        <g className={`${styles.bud} ${styles.budAmber}`} filter="url(#soft-glow)">
          <circle cx="115" cy="205" r="10" fill="#d8a143" />
          <circle cx="115" cy="205" r="5" fill="#fff4cc" />
          <circle cx="115" cy="205" r="16" stroke="#d8a143" strokeWidth="1.5" strokeDasharray="3 3" opacity="0.6" />
        </g>

        {/* Node 2: Mint Bud (Độ vững kiến thức / Real Mastery) */}
        <g className={`${styles.bud} ${styles.budMint}`} filter="url(#soft-glow)">
          <circle cx="175" cy="105" r="12" fill="#63c99a" />
          <circle cx="175" cy="105" r="6" fill="#e3f7eb" />
          <circle cx="175" cy="105" r="19" stroke="#63c99a" strokeWidth="1.5" strokeDasharray="4 2" opacity="0.6" />
        </g>

        {/* Node 3: Aqua Bud (Tư duy phản biện / Crown Apex) */}
        <g className={`${styles.bud} ${styles.budAqua}`} filter="url(#soft-glow)">
          <circle cx="270" cy="40" r="13" fill="#3bb9b0" />
          <circle cx="270" cy="40" r="6.5" fill="#e0faf7" />
          <circle cx="270" cy="40" r="21" stroke="#3bb9b0" strokeWidth="1.8" strokeDasharray="3 3" opacity="0.7" />
        </g>

        {/* Node 4: Sky Bud (Kỹ năng thích ứng / Adaptation) */}
        <g className={`${styles.bud} ${styles.budSky}`} filter="url(#soft-glow)">
          <circle cx="365" cy="105" r="12" fill="#5ca9d6" />
          <circle cx="365" cy="105" r="6" fill="#e3f2fb" />
          <circle cx="365" cy="105" r="19" stroke="#5ca9d6" strokeWidth="1.5" strokeDasharray="4 2" opacity="0.6" />
        </g>

        {/* Node 5: Violet Bud (Tiềm năng cá nhân / Potential) */}
        <g className={`${styles.bud} ${styles.budViolet}`} filter="url(#soft-glow)">
          <circle cx="425" cy="205" r="10" fill="#8578cf" />
          <circle cx="425" cy="205" r="5" fill="#f0edf9" />
          <circle cx="425" cy="205" r="16" stroke="#8578cf" strokeWidth="1.5" strokeDasharray="3 3" opacity="0.6" />
        </g>

        {/* 10. Floating Nature Leaves & Spores */}
        <g className={`${styles.leaf} ${styles.leaf1}`}>
          <path
            d="M210 145 C205 138 212 130 220 133 C225 140 218 148 210 145 Z"
            fill="#9ce0bc"
            opacity="0.85"
          />
        </g>
        <g className={`${styles.leaf} ${styles.leaf2}`}>
          <path
            d="M320 135 C328 128 335 136 331 144 C323 143 317 136 320 135 Z"
            fill="#63c99a"
            opacity="0.8"
          />
        </g>
        <g className={`${styles.leaf} ${styles.leaf3}`}>
          <path
            d="M295 70 C290 62 300 56 306 63 C307 72 299 76 295 70 Z"
            fill="#c3edd5"
            opacity="0.9"
          />
        </g>
      </svg>
    </div>
  );
}
