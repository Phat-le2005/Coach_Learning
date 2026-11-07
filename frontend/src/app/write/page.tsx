import type { Metadata } from "next";
import { DeviceWriter } from "@/features/math-workspace/live/DeviceWriter";

export const metadata: Metadata = {title: "Bảng viết · Coach Learning", robots: {index: false, follow: false}, referrer: "no-referrer"};
export default function WritingDevicePage() {return <DeviceWriter/>;}
