"""
Notification service for sending notifications when transactions succeed.
Supports multiple channels: email, SMS, webhook, push notifications.
"""
import os
import requests
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from models import TxHistory, SwapHistory

load_dotenv()

logger = logging.getLogger(__name__)

# Notification configuration
ENABLE_NOTIFICATIONS = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"
NOTIFICATION_CHANNELS = os.getenv("NOTIFICATION_CHANNELS", "webhook").split(",")  # webhook,email,sms,push

# Webhook configuration
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# Email configuration (using SMTP)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")

# SMS configuration (example: Twilio)
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "")  # twilio, aws-sns, etc.
SMS_API_KEY = os.getenv("SMS_API_KEY", "")
SMS_API_SECRET = os.getenv("SMS_API_SECRET", "")
SMS_FROM_NUMBER = os.getenv("SMS_FROM_NUMBER", "")

# Push notification configuration
PUSH_NOTIFICATION_SERVICE = os.getenv("PUSH_NOTIFICATION_SERVICE", "")  # firebase, onesignal, etc.
PUSH_API_KEY = os.getenv("PUSH_API_KEY", "")


def send_webhook_notification(transaction: TxHistory, recipient_address: str) -> bool:
    """Send notification via webhook"""
    if not WEBHOOK_URL:
        logger.warning("WEBHOOK_URL not configured, skipping webhook notification")
        return False
    
    try:
        payload = {
            "event": "transaction_success",
            "transaction": {
                "tx_hash": transaction.tx_hash,
                "from_address": transaction.from_address,
                "to_address": transaction.to_address,
                "recipient": recipient_address,
                "amount": transaction.amount,
                "token_symbol": transaction.token_symbol,
                "chain": transaction.chain,
                "status": transaction.status,
                "created_at": transaction.created_at.isoformat() if transaction.created_at else None
            }
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if WEBHOOK_SECRET:
            headers["X-Webhook-Secret"] = WEBHOOK_SECRET
        
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"Webhook notification sent successfully for tx {transaction.tx_hash}")
            return True
        else:
            logger.error(f"Webhook notification failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending webhook notification: {str(e)}")
        return False


def send_email_notification(transaction: TxHistory, recipient_address: str, recipient_email: Optional[str] = None) -> bool:
    """Send notification via email"""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping email notification")
        return False
    
    # If recipient_email is not provided, you might need to look it up from a user database
    if not recipient_email:
        logger.warning(f"No email address provided for recipient {recipient_address}")
        return False
    
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = f"Transaction Successful - {transaction.tx_hash[:10]}..."
        
        body = f"""
        Your transaction has been successfully confirmed!
        
        Transaction Details:
        - Hash: {transaction.tx_hash}
        - From: {transaction.from_address}
        - To: {transaction.to_address}
        - Amount: {transaction.amount} {transaction.token_symbol}
        - Chain: {transaction.chain}
        - Status: {transaction.status}
        - Time: {transaction.created_at}
        
        View on explorer: https://etherscan.io/tx/{transaction.tx_hash}
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email notification sent to {recipient_email} for tx {transaction.tx_hash}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        return False


def send_sms_notification(transaction: TxHistory, recipient_address: str, recipient_phone: Optional[str] = None) -> bool:
    """Send notification via SMS"""
    if not SMS_PROVIDER or not SMS_API_KEY:
        logger.warning("SMS not configured, skipping SMS notification")
        return False
    
    if not recipient_phone:
        logger.warning(f"No phone number provided for recipient {recipient_address}")
        return False
    
    try:
        if SMS_PROVIDER.lower() == "twilio":
            from twilio.rest import Client
            client = Client(SMS_API_KEY, SMS_API_SECRET)
            
            message = client.messages.create(
                body=f"Transaction successful! {transaction.amount} {transaction.token_symbol} received. Tx: {transaction.tx_hash[:10]}...",
                from_=SMS_FROM_NUMBER,
                to=recipient_phone
            )
            logger.info(f"SMS notification sent to {recipient_phone} for tx {transaction.tx_hash}")
            return True
        else:
            logger.warning(f"Unsupported SMS provider: {SMS_PROVIDER}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending SMS notification: {str(e)}")
        return False


def send_push_notification(transaction: TxHistory, recipient_address: str, device_token: Optional[str] = None) -> bool:
    """Send push notification"""
    if not PUSH_NOTIFICATION_SERVICE or not PUSH_API_KEY:
        logger.warning("Push notifications not configured, skipping push notification")
        return False
    
    if not device_token:
        logger.warning(f"No device token provided for recipient {recipient_address}")
        return False
    
    try:
        if PUSH_NOTIFICATION_SERVICE.lower() == "firebase":
            # Firebase Cloud Messaging implementation
            import json
            fcm_url = "https://fcm.googleapis.com/fcm/send"
            headers = {
                "Authorization": f"key={PUSH_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "to": device_token,
                "notification": {
                    "title": "Transaction Successful",
                    "body": f"You received {transaction.amount} {transaction.token_symbol}",
                    "sound": "default"
                },
                "data": {
                    "tx_hash": transaction.tx_hash,
                    "amount": str(transaction.amount),
                    "token_symbol": transaction.token_symbol,
                    "chain": transaction.chain
                }
            }
            
            response = requests.post(fcm_url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info(f"Push notification sent for tx {transaction.tx_hash}")
                return True
            else:
                logger.error(f"Push notification failed: {response.status_code}")
                return False
        else:
            logger.warning(f"Unsupported push notification service: {PUSH_NOTIFICATION_SERVICE}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending push notification: {str(e)}")
        return False


def notify_transaction_success(transaction: TxHistory, recipient_address: Optional[str] = None) -> Dict[str, bool]:
    """
    Send notifications when a transaction is successful.
    
    Args:
        transaction: The TxHistory object that was marked as successful
        recipient_address: The recipient address (usually transaction.to_address)
    
    Returns:
        Dictionary with notification channel results
    """
    if not ENABLE_NOTIFICATIONS:
        logger.debug("Notifications are disabled")
        return {}
    
    # Use transaction.to_address as recipient if not provided
    recipient = recipient_address or transaction.to_address
    
    results = {}
    
    # Send notifications via configured channels
    if "webhook" in NOTIFICATION_CHANNELS:
        results["webhook"] = send_webhook_notification(transaction, recipient)
    
    if "email" in NOTIFICATION_CHANNELS:
        # Note: You'll need to implement a way to get email from address
        # This could be from a user database or user preferences
        results["email"] = send_email_notification(transaction, recipient)
    
    if "sms" in NOTIFICATION_CHANNELS:
        # Note: You'll need to implement a way to get phone number from address
        results["sms"] = send_sms_notification(transaction, recipient)
    
    if "push" in NOTIFICATION_CHANNELS:
        # Note: You'll need to implement a way to get device token from address
        results["push"] = send_push_notification(transaction, recipient)
    
    return results


def notify_swap_success(swap: SwapHistory, recipient_address: Optional[str] = None) -> Dict[str, bool]:
    """
    Send notifications when a swap transaction is successful.
    
    Args:
        swap: The SwapHistory object that was marked as successful
        recipient_address: The recipient address
    
    Returns:
        Dictionary with notification channel results
    """
    if not ENABLE_NOTIFICATIONS:
        return {}
    
    recipient = recipient_address or swap.address
    
    # Convert SwapHistory to notification format
    # For now, we'll use webhook as the primary method
    if WEBHOOK_URL:
        try:
            payload = {
                "event": "swap_success",
                "swap": {
                    "tx_hash": swap.tx_hash,
                    "address": swap.address,
                    "from_token_network": swap.from_token_network,
                    "to_token_network": swap.to_token_network,
                    "from_amount": swap.from_amount,
                    "to_amount": swap.to_amount,
                    "status": swap.status,
                    "created_at": swap.created_at.isoformat() if swap.created_at else None
                }
            }
            
            headers = {"Content-Type": "application/json"}
            if WEBHOOK_SECRET:
                headers["X-Webhook-Secret"] = WEBHOOK_SECRET
            
            response = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=10)
            return {"webhook": response.status_code == 200}
        except Exception as e:
            logger.error(f"Error sending swap notification: {str(e)}")
            return {"webhook": False}
    
    return {}

