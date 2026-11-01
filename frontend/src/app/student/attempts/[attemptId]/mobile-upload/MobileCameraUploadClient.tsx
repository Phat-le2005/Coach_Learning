"use client";

import React, { useRef, useState } from "react";
import {
  Camera,
  Image as ImageIcon,
  CheckCircle2,
  RotateCcw,
  UploadCloud,
  Sparkles,
  Loader2,
} from "lucide-react";
import styles from "./MobileUpload.module.css";

interface MobileCameraUploadClientProps {
  attemptId: string;
  token: string;
}

export function MobileCameraUploadClient({
  attemptId,
  token,
}: MobileCameraUploadClientProps) {
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadCount, setUploadCount] = useState(0);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      setErrorMessage("Vui lòng chọn hoặc chụp tệp ảnh (PNG, JPEG).");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setErrorMessage("Ảnh vượt quá kích thước 10 MB. Vui lòng chụp lại ảnh với dung lượng nhỏ hơn.");
      return;
    }

    setErrorMessage(null);
    setSelectedFile(file);
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
  };

  const handleRetake = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    setErrorMessage(null);
    if (cameraInputRef.current) cameraInputRef.current.value = "";
    if (galleryInputRef.current) galleryInputRef.current.value = "";
  };

  const handleUpload = async () => {
    if (!selectedFile || isUploading) return;
    setIsUploading(true);
    setErrorMessage(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const res = await fetch(
        `/api/v3/math-solutions/attempts/${attemptId}/qr-upload?token=${encodeURIComponent(
          token,
        )}`,
        {
          method: "POST",
          headers: {
            "x-qr-upload-token": token,
          },
          body: formData,
        },
      );

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        throw new Error(
          data?.error?.message ||
            data?.message ||
            data?.detail ||
            "Không thể tải ảnh lên máy chủ. Hãy thử lại.",
        );
      }

      setUploadSuccess(true);
      setUploadCount((c) => c + 1);
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Có lỗi xảy ra trong quá trình tải ảnh. Vui lòng thử lại.",
      );
    } finally {
      setIsUploading(false);
    }
  };

  const handleSnapAnother = () => {
    handleRetake();
    setUploadSuccess(false);
  };

  return (
    <div className={styles.uploadCard}>
      <header className={styles.headerBrand}>
        <div className={styles.logoBadge} aria-hidden="true">
          <Sparkles size={20} />
        </div>
        <div>
          <h2 className={styles.headerTitle}>EduMS Living Garden</h2>
          <p className={styles.headerSubtitle}>
            Chụp ảnh bài làm đồng bộ lên máy tính
          </p>
        </div>
      </header>

      {/* Hidden file inputs */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileChange}
        style={{ display: "none" }}
      />
      <input
        ref={galleryInputRef}
        type="file"
        accept="image/png, image/jpeg"
        onChange={handleFileChange}
        style={{ display: "none" }}
      />

      {errorMessage && (
        <div className={styles.alertError} role="alert">
          {errorMessage}
        </div>
      )}

      {/* Step 3: Success Screen */}
      {uploadSuccess ? (
        <div className={styles.successBox}>
          <div className={styles.successIconWrap}>
            <CheckCircle2 size={40} />
          </div>
          <h3 className={styles.successTitle}>Đã gửi ảnh thành công!</h3>
          <p className={styles.successDesc}>
            Trang vở thứ {uploadCount} của bạn đã xuất hiện ngay trên màn hình máy tính.
          </p>
          <div className={styles.successTip}>
            👉 Bạn có thể nhìn lên máy tính để xem khung nhận diện công thức và lưu các bước giải.
          </div>
          <div className={styles.actionButtonGroup} style={{ marginTop: "0.5rem" }}>
            <button
              type="button"
              onClick={handleSnapAnother}
              className={styles.galleryPickBtn}
            >
              <Camera size={16} />
              <span>Chụp thêm trang tiếp theo</span>
            </button>
          </div>
        </div>
      ) : previewUrl ? (
        /* Step 2: Preview Screen */
        <div className={styles.previewStage}>
          <div className={styles.previewFrame}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt="Ảnh bài giải vừa chụp"
              className={styles.previewImg}
            />
          </div>
          <div className={styles.previewActions}>
            <button
              type="button"
              onClick={handleRetake}
              disabled={isUploading}
              className={styles.retakeBtn}
            >
              <RotateCcw size={15} />
              <span>Chụp lại</span>
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={isUploading}
              className={styles.submitBtn}
            >
              {isUploading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  <span>Đang gửi...</span>
                </>
              ) : (
                <>
                  <UploadCloud size={16} />
                  <span>Gửi lên máy tính</span>
                </>
              )}
            </button>
          </div>
        </div>
      ) : (
        /* Step 1: Camera Prompt Screen */
        <div className={styles.promptBox}>
          <div className={styles.cameraHeroIcon}>
            <Camera size={34} />
          </div>
          <div>
            <h3 className={styles.promptHeading}>Chụp ảnh trang vở giải toán</h3>
            <p className={styles.promptHint}>
              Đặt trang vở ở nơi đủ sáng và chụp thẳng góc để AI đọc rõ công thức và bảng biến thiên.
            </p>
          </div>
          <div className={styles.actionButtonGroup}>
            <button
              type="button"
              onClick={() => cameraInputRef.current?.click()}
              className={styles.primaryCameraBtn}
            >
              <Camera size={19} />
              <span>Bật camera chụp ngay</span>
            </button>
            <button
              type="button"
              onClick={() => galleryInputRef.current?.click()}
              className={styles.galleryPickBtn}
            >
              <ImageIcon size={17} />
              <span>Chọn ảnh có sẵn từ thư viện</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
