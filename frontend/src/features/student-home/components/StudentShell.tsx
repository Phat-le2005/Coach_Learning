"use client";
import type { ReactNode } from "react";
import { AppFooter } from "@/components/app-shell/AppFooter";
import { MotionProvider } from "@/components/motion/MotionProvider";
import { HomeAppearance, useHomeAppearance } from "./HomeAppearance";
import { GardenMotionProvider, useGardenMotion } from "./nature/GardenMotionContext";
import { LivingGardenBackdrop } from "./nature/LivingGardenBackdrop";
import { StudentTopNav } from "./StudentTopNav";
import { StudentBottomNav } from "./StudentBottomNav";
import skin from "../StudentSurface.module.css";

function Surface({ children, displayName, email, route, subjectId, footer }: { children: ReactNode; displayName: string; email?: string; route: string; subjectId?: string; footer?: ReactNode }) {
  const { theme } = useHomeAppearance();
  const { ambientEnabled } = useGardenMotion();
  return <div className={skin.surface} data-home-theme={theme} data-garden-motion={ambientEnabled ? "on" : "off"}>
    <LivingGardenBackdrop refined />
    <StudentTopNav displayName={displayName} email={email} currentRoute={route} subjectId={subjectId} showAmbientToggle />
    <div className={skin.content}>{children}</div>
    {footer ?? <AppFooter variant="student" compact />}
    <StudentBottomNav currentRoute={route} subjectId={subjectId} />
  </div>;
}
export function StudentShell(props: Parameters<typeof Surface>[0]) {
  return <HomeAppearance><MotionProvider><GardenMotionProvider><Surface {...props} /></GardenMotionProvider></MotionProvider></HomeAppearance>;
}
