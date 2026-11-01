import type { Metadata } from "next";
import { AlertCircle, QrCode } from "lucide-react";
import { verifyQRUploadToken } from "@/lib/auth/qr-upload-token";
import { MobileCameraUploadClient } from "./MobileCameraUploadClient";
import styles from "./MobileUpload.module.css";

export const metadata: Metadata = {
  title: "Chụp ảnh bài làm gửi lên máy tính · EduMS",
  description: "Trang chụp ảnh bài viết tay nhanh bằng điện thoại đồng bộ lên máy tính.",
};

interface MobileUploadPageProps {
  params: Promise<{ attemptId: string }>;
  searchParams: Promise<{ token?: string }>;
}

export default async function MobileUploadPage(props: MobileUploadPageProps) {
  const { attemptId } = await props.params;
  const { token } = await props.searchParams;

  const tokenPayload = await verifyQRUploadToken(token);
  const isValid = Boolean(tokenPayload && tokenPayload.attemptId === attemptId);

  if (!isValid || !token) {
    return (
      <main className={styles.container}>
        <div className={styles.errorCard}>
          <div className={styles.errorIconWrap}>
            <AlertCircle size={32} color="#b42318" />
          </div>
          <h1 className={styles.errorTitle}>Mã QR đã hết hạn hoặc không đúng</h1>
          <p className={styles.errorDescription}>
            Mã QR chụp ảnh chỉ có hiệu lực trong 20 phút để bảo mật bài làm của bạn.
            Hãy quay lại màn hình máy tính và bấm <strong>&ldquo;Chụp bằng điện thoại&rdquo;</strong> để mở mã QR mới.
          </p>
          <div className={styles.errorTip}>
            <QrCode size={16} />
            <span>Mẹo: Giữ màn hình máy tính mở trong khi quét mã.</span>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.container}>
      <MobileCameraUploadClient attemptId={attemptId} token={token} />
    </main>
  );
}
