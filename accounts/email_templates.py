"""
Beautiful HTML email templates matching the web design
"""

def get_otp_verification_email_template(code: str) -> str:
    """Generate beautiful OTP verification email template"""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verification Code</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: linear-gradient(135deg, #1F2149 0%, #06133F 100%);">
        <table role="presentation" style="width: 100%; border-collapse: collapse; background: linear-gradient(135deg, #1F2149 0%, #06133F 100%);">
            <tr>
                <td style="padding: 40px 20px;">
                    <table role="presentation" style="max-width: 600px; margin: 0 auto; background: rgba(6, 19, 63, 0.75); backdrop-filter: blur(17.5px); border-radius: 24px; border: 1px solid rgba(255, 255, 255, 0.2); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);">
                        <!-- Header -->
                        <tr>
                            <td style="padding: 40px 40px 20px; text-align: center;">
                                <h1 style="margin: 0; color: #ffffff; font-size: 32px; font-weight: 700; letter-spacing: -0.5px;">
                                    Verify Your Email
                                </h1>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 0 40px 30px;">
                                <p style="margin: 0 0 20px; color: rgba(255, 255, 255, 0.8); font-size: 16px; line-height: 1.6; text-align: center;">
                                    Thank you for signing up! Please use the verification code below to complete your registration.
                                </p>
                                
                                <!-- OTP Code Box -->
                                <div style="background: rgba(255, 255, 255, 0.05); border: 2px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 30px; margin: 30px 0; text-align: center;">
                                    <p style="margin: 0 0 15px; color: rgba(255, 255, 255, 0.7); font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">
                                        Your Verification Code
                                    </p>
                                    <div style="background: linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%); border-radius: 12px; padding: 20px; margin: 20px 0;">
                                        <p style="margin: 0; color: #ffffff; font-size: 42px; font-weight: 700; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                                            {code}
                                        </p>
                                    </div>
                                    <p style="margin: 15px 0 0; color: rgba(255, 255, 255, 0.6); font-size: 12px;">
                                        This code will expire in 10 minutes
                                    </p>
                                </div>
                                
                                <p style="margin: 20px 0 0; color: rgba(255, 255, 255, 0.7); font-size: 14px; line-height: 1.6; text-align: center;">
                                    If you didn't request this code, please ignore this email.
                                </p>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="padding: 30px 40px 40px; border-top: 1px solid rgba(255, 255, 255, 0.1); text-align: center;">
                                <p style="margin: 0 0 10px; color: rgba(255, 255, 255, 0.5); font-size: 12px;">
                                    This is an automated message, please do not reply.
                                </p>
                                <p style="margin: 0; color: rgba(255, 255, 255, 0.4); font-size: 11px;">
                                    © 2024 Social Media Platform. All rights reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """


def get_password_reset_email_template(code: str) -> str:
    """Generate beautiful password reset email template"""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Password Reset</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: linear-gradient(135deg, #1F2149 0%, #06133F 100%);">
        <table role="presentation" style="width: 100%; border-collapse: collapse; background: linear-gradient(135deg, #1F2149 0%, #06133F 100%);">
            <tr>
                <td style="padding: 40px 20px;">
                    <table role="presentation" style="max-width: 600px; margin: 0 auto; background: rgba(6, 19, 63, 0.75); backdrop-filter: blur(17.5px); border-radius: 24px; border: 1px solid rgba(255, 255, 255, 0.2); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);">
                        <!-- Header -->
                        <tr>
                            <td style="padding: 40px 40px 20px; text-align: center;">
                                
                                <h1 style="margin: 0; color: #ffffff; font-size: 32px; font-weight: 700; letter-spacing: -0.5px;">
                                    Reset Your Password
                                </h1>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 0 40px 30px;">
                                <p style="margin: 0 0 20px; color: rgba(255, 255, 255, 0.8); font-size: 16px; line-height: 1.6; text-align: center;">
                                    We received a request to reset your password. Use the verification code below to proceed with resetting your password.
                                </p>
                                
                                <!-- OTP Code Box -->
                                <div style="background: rgba(255, 255, 255, 0.05); border: 2px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 30px; margin: 30px 0; text-align: center;">
                                    <p style="margin: 0 0 15px; color: rgba(255, 255, 255, 0.7); font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">
                                        Your Verification Code
                                    </p>
                                    <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 12px; padding: 20px; margin: 20px 0;">
                                        <p style="margin: 0; color: #ffffff; font-size: 42px; font-weight: 700; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                                            {code}
                                        </p>
                                    </div>
                                    <p style="margin: 15px 0 0; color: rgba(255, 255, 255, 0.6); font-size: 12px;">
                                        This code will expire in 10 minutes
                                    </p>
                                </div>
                                
                                <div style="background: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; border-radius: 8px; padding: 15px; margin: 20px 0;">
                                    <p style="margin: 0; color: rgba(255, 255, 255, 0.8); font-size: 13px; line-height: 1.5;">
                                        <strong style="color: #ffffff;">Security Tip:</strong> If you didn't request this password reset, please ignore this email. Your account remains secure.
                                    </p>
                                </div>
                                
                                <p style="margin: 20px 0 0; color: rgba(255, 255, 255, 0.7); font-size: 14px; line-height: 1.6; text-align: center;">
                                    Enter this code in the password reset form to create a new password.
                                </p>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="padding: 30px 40px 40px; border-top: 1px solid rgba(255, 255, 255, 0.1); text-align: center;">
                                <p style="margin: 0 0 10px; color: rgba(255, 255, 255, 0.5); font-size: 12px;">
                                    This is an automated message, please do not reply.
                                </p>
                                <p style="margin: 0; color: rgba(255, 255, 255, 0.4); font-size: 11px;">
                                    © 2024 Social Media Platform. All rights reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

