import time
import typer
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import yaml

CONTEXT_SETTINGS = {
    "help_option_names": ['-h', '--help']
}

app = typer.Typer(context_settings=CONTEXT_SETTINGS, add_completion=False)


def collect_files_to_attach(directory_path: str) -> list:
    file_list = []
    for dirpath, _, filenames in os.walk(directory_path):
        for filename in filenames:
            file_list.append(os.path.join(dirpath, filename))
    return file_list


@app.command()
def send_email_with_attachments(subject: str = typer.Option(..., prompt=True),
                                body: str = typer.Option(..., prompt=True),
                                directory_path: str = typer.Option(..., prompt=True),
                                receiver_email: str = typer.Option(..., prompt=True), has_attachments: bool = True
                                ):
    # Load email configuration from the YAML file
    with open("../config.yml", "r") as config_file:
        config = yaml.safe_load(config_file)

    msg = MIMEMultipart()
    msg["From"] = config["sender_email"]
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if has_attachments:
        attachment_files = collect_files_to_attach(directory_path)

        for file_path in attachment_files:
            file_size = os.path.getsize(file_path)

            if file_size <= config["max_file_size"]:
                with open(file_path, "rb") as file:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(file.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition", f"attachment; filename= {os.path.basename(file_path)}"
                    )
                    msg.attach(part)
            else:
                typer.echo(f"File '{file_path}' exceeds the maximum allowed size and won't be sent.")

    text = msg.as_string()

    try:
        server = smtplib.SMTP(config["smtp_server"], config["smtp_port"])
        server.starttls()
        server.login(config["smtp_username"], config["smtp_password"])

        if has_attachments:
            # Split the attachments into separate emails if necessary
            attachments = msg.get_payload()[1:]  # Skip the text body
            for chunk in chunk_attachments(attachments, config["max_email_size"], config["max_files_per_chunk"]):
                chunk_msg = MIMEMultipart()
                chunk_msg["From"] = config["sender_email"]
                chunk_msg["To"] = receiver_email
                chunk_msg["Subject"] = subject
                chunk_msg.attach(MIMEText(body, "plain"))
                chunk_msg.attach(chunk)
                chunk_text = chunk_msg.as_string()
                server.sendmail(config["sender_email"], receiver_email, chunk_text)
                time.sleep(config["email_delay"])  # Pause before sending the next email
        else:
            server.sendmail(config["sender_email"], receiver_email, text)

        server.quit()
        typer.echo("Email(s) sent successfully!")
    except Exception as e:
        typer.echo(f"Error sending email: {e}")


def chunk_attachments(attachments, max_email_size, max_files_per_chunk=25):
    current_email_size = 0
    current_chunk = MIMEMultipart()
    current_files = 0

    for attachment in attachments:
        attachment_size = len(attachment.as_bytes())
        if current_email_size + attachment_size > max_email_size or current_files >= max_files_per_chunk:
            yield current_chunk
            current_chunk = MIMEMultipart()
            current_email_size = 0
            current_files = 0
        current_chunk.attach(attachment)
        current_email_size += attachment_size
        current_files += 1

    yield current_chunk


@app.command()
def send_email(
        subject: str = typer.Option(..., prompt=True),
        body: str = typer.Option(..., prompt=True),
        directory_path: str = typer.Option(..., prompt=True),
        receiver_email: str = typer.Option(..., prompt=True),
):
    send_email_with_attachments(subject, body, directory_path, receiver_email, False)


if __name__ == '__main__':
    app()
