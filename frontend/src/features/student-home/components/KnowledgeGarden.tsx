"use client";

import Link from "next/link";
import { Trees } from "lucide-react";
import { MathChapterIllustration, getMathChapterType } from "@/features/knowledge-forest/components/MathChapterIllustration";
import { getRegionStateCopy } from "../copy";
import type { KnowledgeRegionViewModel } from "../types";
import ui from "../HomeContent.module.css";
import { HomeIcon } from "./HomeIcon";

export interface KnowledgeGardenProps { regions: KnowledgeRegionViewModel[]; subjectId?: string; }

/** Homepage preview; the full map and its controls stay in the knowledge workspace. */
export function KnowledgeGarden({ regions, subjectId }: KnowledgeGardenProps) {
  const knowledgeHref = `/student/knowledge${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`;
  return <section className={ui.discoverySection} id="knowledge-garden" aria-labelledby="knowledge-garden-title">
    <div className={ui.discoveryHeading}>
      <div><h2 id="knowledge-garden-title">Khu rừng tri thức</h2><p>Nhìn các chủ đề đang học, chọn một nhánh để khám phá tiếp.</p></div>
      <Link className={ui.textAction} href={knowledgeHref}>Mở toàn bộ bản đồ<HomeIcon name="arrow-up-right" size={18} /></Link>
    </div>
    {regions.length > 0 ? <>
      <ul className={ui.regionPreview}>{regions.slice(0, 3).map((region, index) => <li key={region.id}>
        <Link className={ui.regionLink} href={`${knowledgeHref}${subjectId ? "&" : "?"}node=${encodeURIComponent(region.id)}`}>
          <div className={ui.regionDrawing} aria-hidden="true"><MathChapterIllustration type={getMathChapterType(region.label, index)} index={index + 100} /></div>
          <div className={ui.regionName}><h3>{region.label}</h3><HomeIcon name="arrow-up-right" size={18} /></div>
          <p className={ui.regionState}>{getRegionStateCopy(region.state)}{region.progress !== undefined && Number.isFinite(region.progress) ? ` · ${Math.round(region.progress)}%` : ""}</p>
        </Link>
      </li>)}</ul>
      {regions.length > 3 && <p className={ui.previewNote}>Xem trước 3 trong {regions.length} chủ đề. Các nhánh còn lại nằm trong bản đồ tri thức.</p>}
    </> : <div className={ui.forestEmpty}>
      <Trees size={64} strokeWidth={1.25} aria-hidden="true" />
      <div><h3>Khám phá kiến thức theo từng nhánh.</h3><p>Chưa có dữ liệu chủ đề để xem trước tại đây. Bạn vẫn có thể mở bản đồ để khám phá nội dung được phát hành.</p></div>
    </div>}
  </section>;
}
