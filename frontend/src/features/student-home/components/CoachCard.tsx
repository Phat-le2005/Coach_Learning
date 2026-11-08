"use client";

import Link from "next/link";
import { MessageCircleMore } from "lucide-react";
import { getHomeRoutes } from "../home-presentation";
import type { StudentHomeViewModel } from "../types";
import ui from "../HomeContent.module.css";
import { HomeIcon } from "./HomeIcon";

export function CoachCard({ data }: { data: StudentHomeViewModel }) {
  const routes = getHomeRoutes(data);
  return <section className={ui.coachSection} id="coach" aria-labelledby="coach-title">
    <div className={ui.coachCopy}>
      <MessageCircleMore className={ui.coachIcon} size={31} strokeWidth={1.5} aria-hidden="true" />
      <h2 id="coach-title">Trợ lý AI Coach<br />dưới tán cây tri thức</h2>
      <p>Xem phản hồi gắn với từng bước trong bài làm, rồi chọn phần cần xem lại hoặc luyện thêm.</p>
      <div className={ui.actionRow}>
        <Link className={ui.mainAction} href={routes.resume ?? routes.attempts} prefetch={false}>{routes.resume ? "Mở bài đang làm" : "Mở bài tập của tôi"}<HomeIcon name="arrow-right" size={18} /></Link>
        <Link className={ui.textAction} href="/student/theory">Tra cứu lý thuyết<HomeIcon name="book-open" size={18} /></Link>
      </div>
      <p className={ui.coachNote}>Phản hồi AI là gợi ý để kiểm tra lại; điểm chính thức theo đáp án được duyệt hoặc giáo viên.</p>
    </div>
    <ol className={ui.coachFlow} aria-label="Cách xem lại bài làm cùng Coach">
      <li><span className={ui.flowIcon}><HomeIcon name="pen-nib" size={25} /></span><div><h3>Bắt đầu từ bài bạn viết</h3><p>Viết lời giải và kiểm tra bản chép trước khi gửi bài.</p></div></li>
      <li><span className={ui.flowIcon}><HomeIcon name="book-open" size={25} /></span><div><h3>Xem lại từng bước</h3><p>Mở phản hồi trong bài làm để biết phần nào cần xem lại.</p></div></li>
      <li><span className={ui.flowIcon}><HomeIcon name="graph" size={25} /></span><div><h3>Chọn nội dung luyện tiếp</h3><p>Đối chiếu lý thuyết và các ưu tiên học tập của bạn.</p></div></li>
    </ol>
  </section>;
}
