import type { Metadata } from "next";
import { requirePageRole } from "@/lib/auth/page-session";
import { ParentDashboardClient, type ParentTabKey } from "@/features/parent/ParentDashboardClient";

export const metadata: Metadata = {
  title: "Đồng hành Học tập · Cổng Phụ huynh EduMS",
  description: "Theo dõi tiến độ chương trình, thời lượng tự học hàng tuần và gợi ý đồng hành sư phạm cùng con.",
};

interface ParentPageProps {
  searchParams?: Promise<{ tab?: string }>;
}

export default async function ParentPage({ searchParams }: ParentPageProps) {
  const session = await requirePageRole("PARENT", "/parent");
  const params = searchParams ? await searchParams : undefined;
  const validTabs: ParentTabKey[] = ["overview", "curriculum", "weekly", "ai-companion"];
  const initialTab: ParentTabKey = validTabs.includes(params?.tab as ParentTabKey)
    ? (params?.tab as ParentTabKey)
    : "overview";

  return (
    <ParentDashboardClient
      parentName={session.fullName || session.email}
      parentEmail={session.email}
      initialTab={initialTab}
    />
  );
}
