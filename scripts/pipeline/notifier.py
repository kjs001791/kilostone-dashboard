"""
파이프라인 이상치 알림 (이메일)
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

ALERT_THRESHOLD = float(os.getenv("ALERT_REJECTION_THRESHOLD", "5.0"))


def send_alert_email(run_id: int, rows_processed: int, rows_rejected: int, rejection_rate: float):
    """
    이상치 비율 초과 시 알림 이메일 발송.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    alert_email = os.getenv("ALERT_EMAIL")

    if rejection_rate <= ALERT_THRESHOLD:
        return

    if not all([smtp_host, smtp_user, smtp_password, alert_email]):
        print(f"⚠️ [알림 생략] 이상치 비율 {rejection_rate:.1f}% — SMTP 설정 미비")
        return

    subject = f"[KiloStone] 파이프라인 이상치 경고 — {rejection_rate:.1f}%"
    body = (
        f"파이프라인 실행 ID: {run_id}\n"
        f"처리 건수: {rows_processed}건\n"
        f"이상치 건수: {rows_rejected}건\n"
        f"이상치 비율: {rejection_rate:.1f}%\n\n"
        f"설정된 임계값({ALERT_THRESHOLD}%)을 초과했습니다."
    )

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = alert_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, alert_email, msg.as_string())
        print(f"📧 알림 이메일 발송 완료 → {alert_email}")
    except Exception as e:
        print(f"⚠️ 알림 이메일 발송 실패: {e}")
