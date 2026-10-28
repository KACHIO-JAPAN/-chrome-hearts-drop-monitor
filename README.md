# Chrome Hearts drop monitor (experimental)

Independent scheduled monitor for public product links at https://www.chromehearts.com/.

- Runs on GitHub Actions every ~5 minutes, but scheduling is not guaranteed.
- Checks official category links; new URLs trigger a Discord webhook alert only if configured.
- First successful scan creates a baseline; failed scans do not replace prior data.
- Does not yet detect size-specific restocks or products hidden from the five category pages.
- Does not buy anything or bypass access restrictions.

## Set up phone notifications
1. In Discord create a private server and channel for drops.
2. Channel settings → Integrations → Webhooks → New Webhook → Copy Webhook URL. **Never paste the webhook URL in a public GitHub file or chat.**
3. Repository Settings → Secrets and variables → Actions → New repository secret. Name: `DISCORD_WEBHOOK_URL`; paste URL.
4. Repository Actions → Chrome Hearts new-product scan → Run workflow.
5. Check that the scan succeeded and state/products.json was committed. Verify actual notification delivery on the iPhone before relying on it.

Do not treat newly linked items as confirmed Japanese purchasable stock; check the official product URL.
