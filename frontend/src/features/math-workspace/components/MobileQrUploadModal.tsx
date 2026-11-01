"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import QRCode from "qrcode";
import {
  X,
  Smartphone,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Sparkles,
  Copy,
  ExternalLink,
  Wifi,
  AlertTriangle,
} from "lucide-react";
import { refreshBrowserSession } from "@/lib/auth/browser";
import styles from "./MobileQrUploadModal.module.css";

interface MobileQrUploadModalProps {
  attemptId: string;
  accessToken?: string;
  initialFileCount: number;
  onPaperReceived: () => void;
  onClose: () => void;
}

export function MobileQrUploadModal({
  attemptId,
  accessToken,
  initialFileCount,
  onPaperReceived,
  onClose,
}: MobileQrUploadModalProps) {
  const [qrSvg, setQrSvg] = useState<string | null>(null);
  const [uploadPath, setUploadPath] = useState<string | null>(null);
  const [customHost, setCustomHost] = useState<string>("");
  const [isLocalhost, setIsLocalhost] = useState(false);
  const [showLanConfig, setShowLanConfig] = useState(false);
  const [copied, setCopied] = useState(false);

  const [isLoadingToken, setIsLoadingToken] = useState(true);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [receivedSuccess, setReceivedSuccess] = useState(false);
  const [timeLeft, setTimeLeft] = useState(20 * 60);

  const prevFileCountRef = useRef(initialFileCount);

  // Compute final full URL based on origin or custom LAN host
  const getFullUrl = useCallback(
    (path: string) => {
      if (typeof window === "undefined") return path;
      if (customHost.trim()) {
        const protocol = window.location.protocol;
        const host = customHost.trim().replace(/^https?:\/\//i, "");
        return `${protocol}//${host}${path}`;
      }
      return `${window.location.origin}${path}`;
    },
    [customHost],
  );

  // 1. Fetch QR Upload Token
  const fetchToken = useCallback(async () => {
    setIsLoadingToken(true);
    setTokenError(null);
    try {
      const headers: Record<string, string> = {
        Accept: "application/json",
        "X-EduMS-BFF": "1",
      };
      if (accessToken) {
        headers.Authorization = `Bearer ${accessToken}`;
      }

      const safeId = encodeURIComponent((attemptId || "").trim());
      let res = await fetch(`/api/v3/math-solutions/attempts/${safeId}/qr-token`, {
        method: "GET",
        headers,
        cache: "no-store",
        credentials: "same-origin",
      });

      // Auto-retry once on 401 using browser session refresh
      if (res.status === 401) {
        try {
          await refreshBrowserSession();
          res = await fetch(`/api/v3/math-solutions/attempts/${safeId}/qr-token`, {
            method: "GET",
            headers,
            cache: "no-store",
            credentials: "same-origin",
          });
        } catch {
          // Ignore session refresh error and proceed to handle res.status
        }
      }

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        const serverMsg =
          errorData?.error?.message ||
          errorData?.message ||
          errorData?.detail ||
          (res.status === 401
            ? "Phiên đăng nhập đã hết hạn. Vui lòng làm mới trang và đăng nhập lại."
            : res.status === 404
            ? "Không tìm thấy phiên làm bài này để tạo mã QR."
            : `Không thể tạo mã QR lúc này (mã lỗi ${res.status}). Hãy bấm thử lại.`);
        throw new Error(serverMsg);
      }

      const data = await res.json();
      setUploadPath(data.uploadPath);

      const expiresSeconds = Math.max(
        0,
        Math.floor((data.expiresAt - Date.now()) / 1000),
      );
      setTimeLeft(expiresSeconds);
    } catch (err: unknown) {
      console.error("[MobileQrUploadModal] Error fetching QR token:", err);
      setTokenError(
        err instanceof Error ? err.message : "Chưa thể khởi tạo mã QR.",
      );
    } finally {
      setIsLoadingToken(false);
    }
  }, [attemptId, accessToken]);

  useEffect(() => {
    fetchToken();
  }, [fetchToken]);

  // Check if running on localhost
  useEffect(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hostname;
      if (h === "localhost" || h === "127.0.0.1" || h === "::1") {
        setIsLocalhost(true);
      }
    }
  }, []);

  // Update QR SVG when uploadPath or customHost changes
  useEffect(() => {
    if (!uploadPath) return;
    const url = getFullUrl(uploadPath);

    QRCode.toString(url, {
      type: "svg",
      margin: 1,
      color: {
        dark: "#0c3b28",
        light: "#ffffff",
      },
    })
      .then((svg) => {
        setQrSvg(svg);
      })
      .catch((err) => {
        console.error("[MobileQrUploadModal] QR Render error:", err);
      });
  }, [uploadPath, getFullUrl]);

  // 2. Countdown timer
  useEffect(() => {
    if (timeLeft <= 0) return;
    const interval = window.setInterval(() => {
      setTimeLeft((t) => Math.max(0, t - 1));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [timeLeft]);

  // 3. Polling for newly uploaded paper files
  useEffect(() => {
    if (receivedSuccess) return;

    let active = true;
    const safeId = encodeURIComponent((attemptId || "").trim());
    const pollInterval = window.setInterval(async () => {
      try {
        const res = await fetch(
          `/api/v3/math-solutions/attempts/${safeId}/paper`,
          {
            headers: {
              Accept: "application/json",
              "X-EduMS-BFF": "1",
            },
            cache: "no-store",
            credentials: "same-origin",
          },
        );
        if (!res.ok || !active) return;
        const list = await res.json();
        if (Array.isArray(list) && list.length > prevFileCountRef.current) {
          prevFileCountRef.current = list.length;
          setReceivedSuccess(true);
          onPaperReceived();
          window.setTimeout(() => {
            if (active) onClose();
          }, 1400);
        }
      } catch {
        // Continue polling silently
      }
    }, 2400);

    return () => {
      active = false;
      window.clearInterval(pollInterval);
    };
  }, [attemptId, onClose, onPaperReceived, receivedSuccess]);

  // Keyboard shortcut Esc to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleCopyLink = async () => {
    if (!uploadPath) return;
    const url = getFullUrl(uploadPath);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    } catch {
      // Fallback
    }
  };

  const handleOpenDirectly = () => {
    if (!uploadPath) return;
    const url = getFullUrl(uploadPath);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const minutes = Math.floor(timeLeft / 60);
  const seconds = timeLeft % 60;
  const timeFormatted = `${minutes}:${seconds < 10 ? "0" : ""}${seconds}`;

  const currentFullUrl = uploadPath ? getFullUrl(uploadPath) : "";

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true">
      <div className={styles.modalCard}>
        <header className={styles.modalHeader}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <Smartphone size={20} />
            </div>
            <div>
              <h3 className={styles.modalTitle}>
                Chụp ảnh bài làm bằng điện thoại
              </h3>
              <p className={styles.modalSubtitle}>
                Tự động gửi ảnh trang vở lên máy tính của bạn tức thì
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={styles.closeBtn}
            aria-label="Đóng"
          >
            <X size={18} />
          </button>
        </header>

        <div className={styles.modalBody}>
          {receivedSuccess ? (
            <div className={styles.successState}>
              <div className={styles.successIcon}>
                <CheckCircle2 size={44} />
              </div>
              <h4>Đã nhận được ảnh bài làm!</h4>
              <p>
                Ảnh chụp vừa được thêm vào bài làm. Đang đồng bộ và chuyển về màn hình chính...
              </p>
            </div>
          ) : isLoadingToken ? (
            <div className={styles.loadingState}>
              <Loader2 size={32} className="animate-spin" />
              <p>Đang tạo mã QR kết nối an toàn...</p>
            </div>
          ) : tokenError ? (
            <div className={styles.errorState}>
              <div className={styles.errorIconBadge}>
                <AlertTriangle size={24} color="#b42318" />
              </div>
              <p className={styles.errorText}>{tokenError}</p>
              <button
                type="button"
                onClick={fetchToken}
                className={styles.retryBtn}
              >
                <RefreshCw size={14} />
                <span>Thử tạo lại mã</span>
              </button>
            </div>
          ) : (
            <div className={styles.qrContentLayout}>
              <div className={styles.qrFrameWrapper}>
                <div className={styles.qrScanLine} aria-hidden="true" />
                {qrSvg && (
                  <div
                    className={styles.qrSvgContainer}
                    dangerouslySetInnerHTML={{ __html: qrSvg }}
                  />
                )}
                <div className={styles.qrCountdownBadge}>
                  Hiệu lực còn: <strong>{timeFormatted}</strong>
                </div>

                <div className={styles.qrQuickActions}>
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className={styles.quickActionBtn}
                    title="Sao chép liên kết chụp ảnh"
                  >
                    <Copy size={13} />
                    <span>{copied ? "Đã sao chép!" : "Sao chép link"}</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleOpenDirectly}
                    className={styles.quickActionBtn}
                    title="Mở trang chụp ảnh trên tab mới"
                  >
                    <ExternalLink size={13} />
                    <span>Mở tab mới</span>
                  </button>
                </div>
              </div>

              <div className={styles.instructionList}>
                <div className={styles.stepRow}>
                  <div className={styles.stepNum}>1</div>
                  <div className={styles.stepText}>
                    <strong>Mở camera trên điện thoại</strong>
                    <span>
                      Dùng Camera (iPhone) hoặc Google Lens / Zalo / trình duyệt để quét mã QR bên cạnh.
                    </span>
                  </div>
                </div>

                <div className={styles.stepRow}>
                  <div className={styles.stepNum}>2</div>
                  <div className={styles.stepText}>
                    <strong>Chụp trang vở giải toán</strong>
                    <span>
                      Chụp thẳng góc và đủ sáng để hệ thống nhận diện công thức và bảng biến thiên tốt nhất.
                    </span>
                  </div>
                </div>

                <div className={styles.stepRow}>
                  <div className={styles.stepNum}>3</div>
                  <div className={styles.stepText}>
                    <strong>Tự động hiện lên màn hình</strong>
                    <span>
                      Bấm gửi trên điện thoại; ảnh sẽ xuất hiện tức thời trên máy tính để bạn kiểm tra bước giải.
                    </span>
                  </div>
                </div>

                {isLocalhost && (
                  <div className={styles.lanNoticeBox}>
                    <div className={styles.lanNoticeHeader}>
                      <Wifi size={14} />
                      <span>Thử nghiệm trên mạng nội bộ (LAN / Wi-Fi)</span>
                      <button
                        type="button"
                        onClick={() => setShowLanConfig((v) => !v)}
                        className={styles.toggleLanBtn}
                      >
                        {showLanConfig ? "Đóng" : "Đổi IP"}
                      </button>
                    </div>
                    {showLanConfig && (
                      <div className={styles.lanConfigForm}>
                        <label htmlFor="lan-ip-input">
                          Nhập IP máy tính (vd: 192.168.1.15:3000):
                        </label>
                        <input
                          id="lan-ip-input"
                          type="text"
                          placeholder={
                            typeof window !== "undefined"
                              ? `${window.location.hostname}:3000`
                              : "192.168.1.x:3000"
                          }
                          value={customHost}
                          onChange={(e) => setCustomHost(e.target.value)}
                          className={styles.lanInput}
                        />
                      </div>
                    )}
                  </div>
                )}

                <div className={styles.liveListeningBar}>
                  <span className={styles.pulseDot} />
                  <span>Đang lắng nghe kết nối từ điện thoại của bạn...</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {uploadPath && !receivedSuccess && (
          <footer className={styles.modalFooter}>
            <span className={styles.footerNote}>
              <Sparkles size={13} style={{ marginRight: 4, verticalAlign: "middle" }} />
              Không cần đăng nhập lại trên điện thoại.
            </span>
            <button
              type="button"
              onClick={onClose}
              className={styles.cancelBtn}
            >
              Đóng
            </button>
          </footer>
        )}
      </div>
    </div>
  );
}
