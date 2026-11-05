"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Hand, Moon, Pencil, UserRound } from "lucide-react";
import { ACTIVITY_LABELS, classroomActivity, type ClassroomSeat } from "../classroom-model";
import { createClassroomScene, type ClassroomSceneController } from "../classroom-scene";
import styles from "../Classroom3D.module.css";
import type { ClassroomStyles } from "../classroom-personalization";
import cozy from "../CozyCampus.module.css";

interface Props {
  seats: ClassroomSeat[];
  selectedId?: string;
  motion: boolean;
  onSelect: (studentId: string) => void;
  onMascot: () => void;
  onController: (controller: ClassroomSceneController | null) => void;
  customizations: ClassroomStyles;
}

const ActivityIcons = { studying: Pencil, help: Hand, completed: Check, offline: Moon, idle: UserRound };

export default function Classroom3DScene({ seats, selectedId, motion, onSelect, onMascot, onController, customizations }: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const labelRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const controllerRef = useRef<ClassroomSceneController | null>(null);
  const selectRef = useRef(onSelect);
  const mascotRef = useRef(onMascot);
  const bubbleRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");

  useEffect(() => { selectRef.current = onSelect; }, [onSelect]);
  useEffect(() => { mascotRef.current = onMascot; }, [onMascot]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    setStatus("loading");
    let controller: ClassroomSceneController | null = null;
    try {
      controller = createClassroomScene(stage, seats, labelRefs.current, (id) => selectRef.current(id), () => setStatus("unavailable"), () => mascotRef.current(), bubbleRef.current);
      controllerRef.current = controller;
      onController(controller);
      setStatus("ready");
    } catch {
      setStatus("unavailable");
    }
    return () => {
      controller?.dispose();
      controllerRef.current = null;
      onController(null);
    };
  }, [seats, onController]);

  useEffect(() => { controllerRef.current?.select(selectedId); }, [selectedId, status]);
  useEffect(() => { controllerRef.current?.setMotion(motion); }, [motion, status]);
  useEffect(() => { controllerRef.current?.setCustomizations(customizations); }, [customizations, status]);
  const selectedHelp = seats.find((seat) => seat.student?.id === selectedId)?.student?.helpRequest;

  return (
    <div ref={stageRef} className={styles.stage} data-scene-state={status} role="group" aria-label="Lớp học 3D nhìn từ phía giáo viên, 5 hàng, mỗi hàng 2 bàn. Chọn nhân vật hoặc tên học sinh để xem hồ sơ.">
      <div className={styles.sceneTags} aria-hidden="true"><span>Góc nhìn giáo viên</span><span>5 hàng × 2 bàn</span></div>
      <div ref={bubbleRef} className={cozy.speechBubble} hidden={!selectedHelp} aria-hidden="true">Thầy cô ơi! ✋</div>
      {status !== "ready" && <p className={styles.sceneMessage} role="status">{status === "loading" ? "Đang mở lớp học 3D…" : "Chưa hiển thị được 3D trên thiết bị này. Chọn học sinh bên dưới để xem hồ sơ."}</p>}
      <div className={styles.seatLabels}>
        {seats.map((seat, index) => {
          const student = seat.student;
          const activity = student ? classroomActivity(student) : "idle";
          const Icon = ActivityIcons[activity];
          const shortName = student?.name.replace(/\s*\(Demo\s*\d+\)\s*$/i, "").split(" ").slice(-2).join(" ");
          return (
            <button
              ref={(node) => { labelRefs.current[index] = node; }}
              key={student?.id ?? `empty-${seat.number}`}
              type="button"
              className={styles.seatLabel}
              data-activity={activity}
              data-empty={!student}
              data-seat-index={index}
              data-student-id={student?.id}
              aria-pressed={Boolean(student && student.id === selectedId)}
              aria-label={student ? `${student.name}, bàn ${seat.number}, ${ACTIVITY_LABELS[activity]}` : `Bàn ${seat.number} trống`}
              title={student?.name ?? `Bàn ${seat.number} trống`}
              disabled={!student}
              onClick={() => student && onSelect(student.id)}
            >
              <Icon size={13} aria-hidden="true" />
              <span className={styles.seatName}>{shortName ?? "Trống"}</span>
              <span className={styles.seatNumber}>Bàn {seat.number}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
