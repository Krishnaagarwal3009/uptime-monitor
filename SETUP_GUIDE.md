# Website Uptime Monitor: Complete Setup Guide (Oracle VM)

Follow the parts in order. Do not skip any. Total time: about 30 minutes.

**What you will have at the end**
- Your sites are checked every 5 minutes, 24/7, from your Oracle VM (not from MilesWeb, so it still works when MilesWeb is down).
- Telegram messages: 🔴 DOWN, 🟢 RECOVERED with the exact downtime, and a daily 24-hour report at 8 AM.
- Full logs saved on the VM that you can share with MilesWeb.

**Key rules**
- Your Amazon inventory bot keeps running untouched. We only add a NEW folder and a NEW service.
- You need a SECOND Telegram bot for this. Never reuse the inventory bot's token (the two would fight each other and break the inventory bot).
- Text in `grey code boxes` is typed or pasted in the terminal, and then you press Enter.
- To paste in the PowerShell or SSH window, right-click. Ctrl+V often doesn't work in it.

---

## PART A: Telegram (on your phone or Telegram Desktop)

### A1. Create the new bot
1. Open Telegram and search for **@BotFather**. It has a blue verified tick.
2. Press **Start**, then send: `/newbot`
3. It asks for a name. Send: `Website Uptime Monitor`
4. It asks for a username. It must end with `bot` and be unique, for example `krishna_uptime_bot`. If it says taken, try another.
5. BotFather replies with a **token** that looks like `1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`. Copy it and keep it secret. Paste it into a private note for now.

### A2. Wake up the bot (required)
1. Click the link BotFather gives you (`t.me/your_bot_username`), or search for your new bot's username.
2. Press **Start** (or send "hi"). A bot can't message you until you do this.

### A3. Get your chat ID
1. Search for **@userinfobot** and press **Start**. It replies with `Id: 123456789`.
2. That number is your **chat ID**. Save it with the token.
   (It is the same number as `YOUR_CHAT_ID` in your inventory bot's config.)

You now have two things: the **token** and the **chat ID**.

---

## PART B: GitHub cleanup (on your laptop browser)

Your GitHub copy of the monitor must be switched off so you don't get duplicate alerts.

1. Go to https://github.com/Krishnaagarwal3009/uptime-monitor/actions
2. In the left list click **monitor**, then click the **⋯** (three dots) at the top right, then **Disable workflow**.
3. Do the same for **daily-report**. Leave **test-telegram** as it is. It only runs when you click it.
4. Open `config.json` in the repo and click the pencil (edit) icon. Make sure the sites list contains ONLY your real sites, with no `thisdoesnotexist` line:
   ```
   "sites": [
     "https://projectsaas.in",
     "https://imprest.projectsaas.in"
   ],
   ```
   Click **Commit changes**.

---

## PART C: Oracle Cloud website (collect the VM address)

1. Go to https://cloud.oracle.com and sign in.
2. Open the menu (☰, top left), then **Compute**, then **Instances**.
3. Make sure the correct **Region** (top right) and **Compartment** are selected. This is the same place where your inventory VM lives.
4. Click your instance name (the one running your Amazon bot).
5. Check that the state shows **Running** in green.
6. Find **Public IP address** (for example `140.238.xx.xx`). Copy it. This is your VM address. It stays the same.
7. Find your **SSH private key file**. It is the `.key` or `.pem` file you downloaded when you created the VM, and you use it to connect for your inventory bot. Note where it is saved, for example `C:\Users\agarw\Downloads\ssh-key.key`.

No firewall or Security List changes are needed. The monitor only makes outgoing connections.

---

## PART D: Connect to the VM (on your laptop)

1. Press the **Windows key**, type **PowerShell**, and open **Windows PowerShell**.
2. Type this, replacing the two parts in `<>` with your key path and IP:
   ```
   ssh -i "C:\Users\agarw\Downloads\ssh-key.key" ubuntu@<YOUR-VM-IP>
   ```   
3. If it asks `Are you sure you want to continue connecting?` type `yes` and press Enter.
4. You are in when the prompt looks like `ubuntu@something:~$`.

**If it fails**
- "Permission denied (publickey)" means the key or username is wrong. Oracle Ubuntu images use `ubuntu`. Oracle Linux images use `opc`.
- "UNPROTECTED PRIVATE KEY FILE" means Windows is complaining about file permissions. Run these two commands, and then try again:
  ```
  icacls "C:\Users\agarw\Downloads\ssh-key.key" /inheritance:r
  icacls "C:\Users\agarw\Downloads\ssh-key.key" /grant:r "$($env:USERNAME):(R)"
  ```
- If you already use another tool to connect for your inventory bot (PuTTY, MobaXterm, VS Code), use that. All the commands below are the same.

Every command from here on is typed inside this SSH window, until Part G.

---

## PART E: Safety checks (nothing is changed)

Run these one at a time and read the output.

```
ls ~
```
You should see `amazon-bot`. You must NOT already see `uptime-monitor`.

```
python3 --version
git --version
```
Both should print a version number (Python 3.8 or newer). If one says "command not found", run:
```
sudo apt update && sudo apt install -y python3 git
```

```
date
free -m
df -h /
```
- `date` should show IST (Asia/Kolkata), which matches your inventory setup.
- `free -m` should show at least 100 MB free in the `available` column.
- `df -h /` should show some free space.

```
pm2 status
```
Note that `inventory-bot` is `online`. You will run this again at the end to confirm it's unchanged.

---

## PART F: Install the monitor

### F1. Download the code
```
cd ~
git clone https://github.com/Krishnaagarwal3009/uptime-monitor.git
cd uptime-monitor
ls
```
You should see files like `monitor.py`, `report.py`, `common.py`, `config.json`.

### F2. Check the sites list
```
cat config.json
```
It must list only your real sites. If it still contains `thisdoesnotexist`, fix it:
```
nano config.json
```
Use the arrow keys, delete the bad line, and make sure the last site has NO comma after it. To save: press **Ctrl+O**, then **Enter**, then **Ctrl+X** to exit.

To add more sites later, copy a line, put a comma after every line except the last, and keep the quotes.

---

## PART G: Save the Telegram secrets on the VM

```
sudo nano /etc/uptime-monitor.env
```
In the editor, type these two lines. Use YOUR real values from Part A. No spaces around `=`, no quotes:
```
TELEGRAM_BOT_TOKEN=1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789
```
Save: **Ctrl+O**, **Enter**, **Ctrl+X**. Then lock the file so only you can read it:
```
sudo chown ubuntu:ubuntu /etc/uptime-monitor.env
sudo chmod 600 /etc/uptime-monitor.env
```
(If your username is not `ubuntu`, put your username in place of `ubuntu` here and in Part I.)

---

## PART H: Test before turning it on

```
cd ~/uptime-monitor
set -a; . /etc/uptime-monitor.env; set +a
python3 monitor.py --test
```
**Expected:** a message "✅ Test message from uptime monitor" arrives from your NEW bot in Telegram within a few seconds.

If it does NOT arrive:
- Make sure you pressed Start on the new bot (A2).
- Check the token and chat ID with `cat /etc/uptime-monitor.env`. There must be no typos, spaces or quotes.
- Check internet access from the VM with `curl -I https://api.telegram.org`.

Now run one check:
```
python3 monitor.py
```
**Expected:** two lines saying `UP 200` for your two sites.

Run a sample report:
```
python3 report.py
```

Clean up the test data so the real logs start fresh:
```
rm -f data/checks-*.csv data/state.json reports/*.txt
```

---

## PART I: Make it run 24/7 (auto-start, auto-restart)

Copy and paste this whole block at once:
```
sudo tee /etc/systemd/system/uptime-monitor.service >/dev/null <<'EOF'
[Unit]
Description=Website uptime monitor
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/uptime-monitor
EnvironmentFile=/etc/uptime-monitor.env
ExecStart=/usr/bin/python3 monitor.py --daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```
Then turn it on:
```
sudo systemctl daemon-reload
sudo systemctl enable --now uptime-monitor
sudo systemctl status uptime-monitor --no-pager
```
**Expected:** a green `active (running)`.

Watch the live checks:
```
journalctl -u uptime-monitor -f
```
You should see an UP line for each site. Press **Ctrl+C** to stop watching. The monitor keeps running.

---

## PART J: Daily report at 8:00 AM IST

```
crontab -l
```
Note your two existing inventory lines. Don't touch them. Then:
```
crontab -e
```
(If it asks which editor, choose `nano`.) Use the arrow keys to go to the very bottom, and add this as a NEW line after the existing ones:
```
0 8 * * * cd /home/ubuntu/uptime-monitor && set -a && . /etc/uptime-monitor.env && set +a && python3 report.py --send
```
Save: **Ctrl+O**, **Enter**, **Ctrl+X**. Confirm with `crontab -l`. You should see all three lines.

Test it immediately without waiting for 8 AM:
```
cd ~/uptime-monitor && set -a && . /etc/uptime-monitor.env && set +a && python3 report.py --send
```
A report should arrive in Telegram.

**Your daily report doubles as a health check.** If a morning passes with no report, the VM or the monitor is down.

---

## PART K: Test a real alert

```
cd ~/uptime-monitor
nano config.json
```
Add a fake site as a new line in the list (remember the comma on the line above it):
```
    "https://projectsaas.in",
    "https://imprest.projectsaas.in",
    "https://thisdoesnotexist.projectsaas.in"
```
Save, then restart:
```
sudo systemctl restart uptime-monitor
```
**Expected within about 1–2 minutes:** a 🔴 DOWN message for the fake site.

Now undo it: open `nano config.json` again, delete the fake line (and the comma that came before it), save, and restart:
```
sudo systemctl restart uptime-monitor
```
**Expected:** a 🟢 RECOVERED message may arrive or the fake site just disappears from checks. Either is fine.

---

## PART L: Final check that your inventory bot is untouched

```
pm2 status
crontab -l
```
`inventory-bot` should still be `online`, and your two original cron lines should still be there.

Everything is done. Type `exit` to leave the VM.

---

## Daily use cheat-sheet (inside the SSH window)

| What you want | Command |
|---|---|
| See live checks | `journalctl -u uptime-monitor -f` (Ctrl+C to leave) |
| Is it running? | `sudo systemctl status uptime-monitor --no-pager` |
| Restart | `sudo systemctl restart uptime-monitor` |
| Stop it | `sudo systemctl stop uptime-monitor` |
| Start it | `sudo systemctl start uptime-monitor` |
| Today's report now | `cd ~/uptime-monitor && set -a && . /etc/uptime-monitor.env && set +a && python3 report.py --send` |
| Send a test message | `cd ~/uptime-monitor && set -a && . /etc/uptime-monitor.env && set +a && python3 monitor.py --test` |
| Change check interval | Edit `config.json`: `normal_interval_seconds` (300 = 5 min), then restart |
| Check faster when down | Edit `config.json`: `down_recheck_seconds` (120 = 2 min), then restart |
| Add a site | Add a line in `config.json`, then restart |
| Update to my newest code | `cd ~/uptime-monitor && git pull && sudo systemctl restart uptime-monitor` |

## Where your logs are (for MilesWeb)

All in `/home/ubuntu/uptime-monitor/`:
- `data/checks-YYYY-MM.csv`: every check (time, site, up/down, HTTP code, response time, error)
- `data/incidents.csv`: every outage (start, end, duration in seconds, reason)
- `reports/report-YYYY-MM-DD.txt`: the daily 24-hour reports

Times in the logs are in UTC. Reports and Telegram messages show IST. To copy the logs to your laptop, open a normal PowerShell window (not the SSH one) and run:
```
scp -i "C:\Users\agarw\Downloads\ssh-key.key" -r ubuntu@<YOUR-VM-IP>:~/uptime-monitor/data "D:\Documents\Claude Projects\Website Track up and down\vm-logs"
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Service shows `failed` | Run `journalctl -u uptime-monitor -n 30 --no-pager` and read the error. A common one is a typo in `config.json` (a missing comma). |
| No Telegram messages | Run the `--test` command from the cheat-sheet. Check the token and chat ID in `/etc/uptime-monitor.env`, and that you pressed Start on the new bot. |
| Too many "STILL DOWN" messages | Raise `still_down_reminder_minutes` in `config.json`, then restart. |
| False DOWN alerts | Raise `timeout_seconds` (default 20) or `confirm_retries` in `config.json`. |
| Worried about the inventory bot | Run `pm2 status`. It should show `online`. The monitor doesn't touch it. |
| Want to remove everything | `sudo systemctl disable --now uptime-monitor`, then `sudo rm /etc/systemd/system/uptime-monitor.service`, delete the `~/uptime-monitor` folder, and remove the cron line in `crontab -e`. |

## PART 2: Telegram commands (update the VM)

Do this only after Parts A to L work.

### 2.1 Update the code (inside the SSH window)
```
cd ~/uptime-monitor
git checkout -- config.json
git pull
```
`git checkout -- config.json` discards the VM's local edit of the sites list. The new version on GitHub already contains your two real sites. If you added more sites on the VM, add them again later with `/add` in Telegram.

### 2.2 Turn on PDF reports (isolated, does not touch your inventory bot's packages)
```
sudo apt install -y python3-venv
python3 -m venv ~/uptime-monitor/venv
~/uptime-monitor/venv/bin/pip install fpdf2
```

### 2.3 Point the service at the new Python and restart
```
sudo sed -i 's#ExecStart=/usr/bin/python3 monitor.py --daemon#ExecStart=/home/ubuntu/uptime-monitor/venv/bin/python monitor.py --daemon#' /etc/systemd/system/uptime-monitor.service
sudo systemctl daemon-reload
sudo systemctl restart uptime-monitor
sudo systemctl status uptime-monitor --no-pager
journalctl -u uptime-monitor -n 10 --no-pager
```
The status should show `active (running)` with the `venv/bin/python` command and no `Traceback`.

### 2.4 Remove the old cron line for the daily report
The service now sends the daily report itself (default 8:00 AM IST, change it with `/reporttime`). Run `crontab -e` and delete the `report.py --send` line. Leave your inventory lines alone.

### 2.5 Use it
Open your **uptime bot** in Telegram and send `/start`. A button keyboard appears.

| Command | What it does |
|---|---|
| `/status` | Live status of every site |
| `/check` | Check all sites right now |
| `/report` or `/report 6h` or `/report 7d` | Pretty report in the chat |
| `/pdf` or `/pdf 24h` | PDF report file to send to MilesWeb |
| `/csv` or `/csv 24h` | Two CSV files: every check, and every outage |
| `/interval 2m` | Check normal sites every 2 minutes (minimum 30s) |
| `/downinterval 30s` | While a site is down, recheck every 30 seconds (minimum 15s) |
| `/timeout 20` | Seconds before a check counts as failed |
| `/reminder 30` | "Still down" reminder every N minutes |
| `/add https://x.com` and `/remove x.com` | Add or remove a monitored site |
| `/sites` | List sites |
| `/pause` and `/resume` | Stop or start checks and alerts (e.g. during maintenance) |
| `/reporttime 8` | Hour (IST) of the daily report |
| `/settings` | Show all settings |

Settings changed in Telegram are saved in `data/settings.json` on the VM and apply at once. Only your own chat ID can use the bot.

If the commands do nothing, check `journalctl -u uptime-monitor -n 30 --no-pager`. A "409 Conflict" means another program is using the SAME bot token. Each bot needs its own token.
