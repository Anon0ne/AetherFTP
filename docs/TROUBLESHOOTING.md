# Troubleshooting

[Back to README](../README.md) · [Usage](USAGE.md)

Open **Transfer activity > Event log**. Connection steps and server replies help identify the failing operation. GUI errors show exception types; the Event log provides additional detail.

| Symptom | Check |
| --- | --- |
| FTPES SSL error | Use explicit TLS and the correct port. Check the server certificate's hostname, expiry and trust chain, passive data ports and the logged TLS handshake. Session reuse is enabled; certificate verification is not bypassed. |
| `421` too many connections | Reduce concurrent uploads/downloads in Menu > Settings. Browsing adds a connection per connected tab. Other clients from your IP also count. Idle transfer connections close after the queue drains. |
| `553` could not create file | Check remote destination, server write permissions, quota, free space and name conflicts. This is a server rejection, not proof folder upload is unsupported. |
| Local PermissionError | Open the real target folder. The app resolves the current user's legacy My Documents alias, but respects permissions on its target. |
| SFTP host-key rejection | Independently verify the server key, then enroll it in `%USERPROFILE%\.ssh\known_hosts`. Unknown keys are rejected. |
| Close says operations remain | Choose Stop and exit. It cancels pending work and waits for workers to finish; connection setup can take up to its timeout. Finish remote editing sessions first. |
| New work after Stop | Reconnect before queuing transfers. Partial files remain; enable resume only for the matching source. |
| Shortcut stops working | Keep the extracted folder in place, or rerun the shortcut helper from the new folder. |
| Source installation fails | Review the BAT/PowerShell output, Python version, internet access and disk space. Test failures stop the build. |

Persistent rotating JSON logs are under `%APPDATA%\AetherFTP\logs`. Include app version, protocol, the failed operation and relevant redacted Event log lines in a [GitHub issue](https://github.com/Anon0ne/AetherFTP/issues). Do not include passwords, tokens, private keys, server profiles or private remote-editing copies. Review unexpected server replies before sharing.
