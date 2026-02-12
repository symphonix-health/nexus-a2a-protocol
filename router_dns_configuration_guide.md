# Router DNS Configuration Guide

**Date:** February 11, 2026
**Goal:** Update router WAN DNS to use Cloudflare (1.1.1.1) and Google DNS (8.8.8.8)

## Step 1: Access Router Admin Interface

**Your Router Address:** `http://192.168.1.254`

1. Open a web browser (Chrome, Edge, Firefox, etc.)
2. Navigate to: **<http://192.168.1.254>4>**
3. Log in with your router admin credentials
   - Common defaults: admin/admin, admin/password, admin/[blank]
   - Check the sticker on your router for specific credentials
   - May also be printed on bottom/back of router

## Step 2: Locate WAN DNS Settings

Router interfaces vary by manufacturer, but typically:

### Common Router Paths

- **TP-Link:** Advanced → Network → Internet → Advanced Settings → DNS
- **Netgear:** Advanced → Setup → Internet Setup → DNS Addresses
- **Asus:** WAN → Internet Connection → WAN DNS Setting
- **Linksys:** Connectivity → Internet Settings → DNS
- **D-Link:** Setup → Internet → Manual Internet Connection Setup
- **Google Wifi/Nest:** Google Home app → WiFi → Settings → Advanced networking → DNS

### Look for sections labeled

- WAN Settings
- Internet Settings
- Internet Connection
- DNS Settings
- Primary/Secondary DNS

## Step 3: Update DNS Servers

**IPv4 DNS Servers:**

- Primary DNS: `1.1.1.1` (Cloudflare)

- Secondary DNS: `8.8.8.8` (Google DNS)

**IPv6 DNS Servers (if available):**

- Primary IPv6: `2606:4700:4700::1111` (Cloudflare)
- Secondary IPv6: `2001:4860:4860::8888` (Google DNS)

### Configuration Options

Most routers have these options:

- ☐ **Automatic (from ISP)** - Currently failing, need to change this
- ☑ **Manual/Static DNS** - Select this option
- Then enter the DNS addresses above

## Step 4: Save and Restart

1. Click **Save** or **Apply** button
2. Router may restart automatically (1-3 minutes)
3. If not, manually reboot the router:
   - Power cycle: Unplug for 10 seconds, plug back in
   - Or use the reboot option in router admin interface

## Step 5: Verify on All Devices

After router restarts:

```powershell
# On Windows (PowerShell):
ipconfig /flushdns
nslookup example.com

# Should show:

# Server: one.one.one.one
# Address: 1.1.1.1
```

On other devices:

- Reconnect to WiFi (optional, but recommended)
- DNS should now work automatically

## Benefits of This Approach

✅ **Network-wide fix:** All devices automatically use reliable DNS
✅ **No per-device configuration:** Works for phones, tablets, IoT devices, etc.
✅ **Backup DNS:** If Cloudflare is down, Google DNS takes over

✅ **Performance:** Both are fast, global DNS providers
✅ **Privacy:** Better than ISP DNS (no logging/tracking)

## Troubleshooting

### Can't access router admin page?

- Check if you're connected to the network
- Try common IPs: `192.168.1.1`, `192.168.0.1`, `10.0.0.1`
- Look at router sticker for default gateway
- Check router manual or manufacturer website

### Don't know router password?

- Check router sticker for defaults
- Try: admin/admin, admin/password, admin/[blank]
- If forgotten: May need to factory reset router (last resort)
- Contact ISP if they provided/manage the router

### Changes not taking effect?

- Clear DNS cache on your device: `ipconfig /flushdns`
- Restart your device
- Power cycle the router completely
- Ensure you saved changes and router restarted

### ISP-provided router won't let you change DNS?

- Some ISP routers lock DNS settings
- Options:
  1. Contact ISP to unlock or change settings
  2. Use per-device DNS (as you did on WiFi 2)
  3. Add your own router behind ISP router (bridge mode)

## Rollback Instructions

If issues occur, revert to automatic DNS:

1. Return to router DNS settings
2. Select "Automatic" or "Obtain DNS automatically from ISP"
3. Save and restart router

---

## Alternative: Per-Device Configuration

If you can't change router settings, configure DNS on each device individually (like you did for WiFi 2):

**Windows:**
Network Connections → WiFi Properties → IPv4/IPv6 → Use these DNS servers

**macOS:**
System Preferences → Network → Advanced → DNS → + button

**iOS/Android:**
WiFi Settings → Configure DNS → Manual → Add 1.1.1.1, 8.8.8.8

**Linux:**
`/etc/resolv.conf` or NetworkManager settings
