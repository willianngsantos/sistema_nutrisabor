"""
Utilitário de envio de e-mail via Resend (https://resend.com).
Usa a variável RESEND_API_KEY do .env
"""
import os
import resend


def send_email(destinatario: str, assunto: str, corpo_html: str) -> bool:
    """
    Envia um e-mail via Resend API.
    Retorna True em caso de sucesso, False em caso de erro.
    """
    api_key = os.environ.get('RESEND_API_KEY', '')
    remetente = os.environ.get('MAIL_FROM', 'NutriSabor <noreply@nutrisabor.sistemaswgs.com.br>')

    if not api_key:
        print("❌ RESEND_API_KEY não configurada no .env")
        return False

    resend.api_key = api_key

    try:
        resend.Emails.send({
            "from": remetente,
            "to": [destinatario],
            "subject": assunto,
            "html": corpo_html,
        })
        return True
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")
        return False


def email_codigo(destinatario: str, codigo: str, tipo: str) -> bool:
    """
    Envia o e-mail com o código de 6 dígitos.
    tipo: 'primeiro_acesso' ou 'reset_senha'
    """
    if tipo == 'primeiro_acesso':
        assunto = "Seu código de acesso - NutriSabor"
        titulo = "Bem-vindo ao NutriSabor!"
        mensagem = "Seu cadastro foi criado. Use o código abaixo para definir sua senha e acessar o sistema."
    else:
        assunto = "Redefinição de senha - NutriSabor"
        titulo = "Redefinição de Senha"
        mensagem = "Recebemos uma solicitação para redefinir sua senha. Use o código abaixo para criar uma nova."

    corpo_html = f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 0;">
        <tr>
          <td align="center">
            <table width="420" cellpadding="0" cellspacing="0"
                   style="background:#ffffff;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.08);overflow:hidden;">
              <!-- Header -->
              <tr>
                <td style="background:linear-gradient(135deg,#0f172a,#14532d);padding:24px 32px;text-align:center;">
                  <img src="https://nutrisabor.sistemaswgs.com.br/static/img/logo.png"
                       alt="NutriSabor" style="max-height:70px; display:block; margin:0 auto;">
                </td>
              </tr>
              <!-- Body -->
              <tr>
                <td style="padding:32px;">
                  <h2 style="color:#1e293b;font-size:20px;margin:0 0 12px;">{titulo}</h2>
                  <p style="color:#64748b;font-size:15px;line-height:1.6;margin:0 0 28px;">{mensagem}</p>

                  <!-- Código -->
                  <div style="background:#f8fafc;border:2px dashed #16a34a;border-radius:10px;
                              padding:20px;text-align:center;margin:0 0 28px;">
                    <p style="color:#64748b;font-size:12px;text-transform:uppercase;
                               letter-spacing:2px;margin:0 0 8px;">Código de verificação</p>
                    <span style="color:#16a34a;font-size:40px;font-weight:bold;letter-spacing:10px;">
                      {codigo}
                    </span>
                  </div>

                  <p style="color:#94a3b8;font-size:13px;margin:0;">
                    ⏱️ Este código expira em <strong>15 minutos</strong>.<br>
                    Se você não solicitou, ignore este e-mail.
                  </p>
                </td>
              </tr>
              <!-- Footer -->
              <tr>
                <td style="background:#f8fafc;padding:16px 32px;text-align:center;
                            border-top:1px solid #e2e8f0;">
                  <p style="color:#cbd5e1;font-size:12px;margin:0;">
                    NutriSabor — Sistema de Gestão
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

    return send_email(destinatario, assunto, corpo_html)
