# Reply tracking

A reply carries the original message's `Message-ID` in its `In-Reply-To` /
`References` headers. iceReach sent that `Message-ID`, so it matches replies to
the exact campaign that was sent — scoped to your workspace, idempotent (one
reply counted per sent message). Replies show up as the **Replies** metric in
campaign analytics.

## Recommended: IMAP

iceReach polls your mailbox over IMAP and matches replies. It selects the inbox
**read-only** (never marks mail as read or deletes it) and fetches **only new
messages** incrementally (UID high-water mark), pulling just the
`In-Reply-To`/`References` headers — so it's cheap and non-intrusive.

**Setup** — iceReach → Settings → (your domain) → *Set up reply tracking*:

| Field | Value |
|------|-------|
| Protocol | **IMAP** |
| Host | `imap.zoho.in` (or your provider's IMAP host) |
| Port | `993` |
| Mailbox username | the mailbox you send from, e.g. `team@influenceai.in` |
| Mailbox password | that mailbox's password / app password |
| Reply-To | **leave blank** (replies go to your From address, which is this mailbox) |

Save. The worker polls every ~2 minutes; replies appear in each campaign's
analytics.

> **IMAP must be enabled on your mail plan.** On Zoho, IMAP access requires a
> paid plan (Settings → Mail Accounts → IMAP). If you can't enable it, use the
> free inbound-webhook fallback below.

## Fallback (no paid IMAP): inbound webhook

Forward replies to iceReach's inbound webhook instead of polling a mailbox.

1. Settings → *Set up reply tracking* → copy the **inbound webhook URL**
   (`https://YOUR_PUBLIC_HOST/webhooks/inbound/<token>`), set Protocol = **Off**,
   and set **Reply-To** to an address on a reply subdomain
   (e.g. `reply@reply.influenceai.in`).
2. Point that subdomain's MX at a free inbound-parse service that POSTs to the
   webhook — **SendGrid Inbound Parse** is simplest (one GoDaddy MX record →
   `mx.sendgrid.net`, no nameserver change). A Cloudflare Email Worker also
   works:
   ```js
   export default {
     async email(message, env) {
       const raw = await new Response(message.raw).arrayBuffer();
       await fetch(env.ICEREACH_WEBHOOK_URL, {
         method: "POST",
         headers: { "content-type": "message/rfc822" },
         body: raw,
       });
     },
   };
   ```
The webhook accepts raw RFC822, multipart form (`email`/`raw`/`headers`), or
JSON (`raw`, or `in_reply_to`/`references`).

> The webhook host must be **publicly reachable** — set `BASE_URL` to a deployed
> URL or a tunnel (`cloudflared tunnel --url http://localhost:8000`), not
> `127.0.0.1`.

## Self-test (either path)

```bash
curl -X POST "$BASE_URL/webhooks/inbound/<token>" \
  -H "content-type: message/rfc822" \
  --data-binary $'In-Reply-To: <A-REAL-SENT-MESSAGE-ID>\r\n\r\nyes interested'
# -> {"recorded": true}
```

## Limit

If a recipient's reply strips the `In-Reply-To`/`References` headers (rare — some
web forms, or composing a brand-new email instead of hitting Reply), it can't be
matched. A normal "Reply" from any mail client includes them.
