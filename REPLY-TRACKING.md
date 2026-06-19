# Reply tracking (free, keeps Zoho) — inbound webhook setup

Zoho gates POP **and** IMAP behind paid plans, so iceReach can't poll your Zoho
mailbox. Instead it exposes an **inbound webhook**: forward replies to it and
they're matched to the campaign that was sent (by `Message-ID`) and counted as
**Replies** in campaign analytics.

You never move your main mail off Zoho. You only add a **reply subdomain** whose
mail goes to a free inbound-parse service that POSTs to the webhook.

```
Recipient hits "Reply"  ─►  goes to your Reply-To (reply@reply.influenceai.in)
                         ─►  subdomain MX → inbound-parse service (free)
                         ─►  service POSTs the email → iceReach webhook
                         ─►  matched by Message-ID → "Replies" in analytics
```

## 0. Get your webhook URL

iceReach → **Settings → (your domain) → Set up reply tracking**. Copy the
**inbound webhook URL** shown there. It looks like:

```
https://YOUR_PUBLIC_HOST/webhooks/inbound/<token>
```

> The host must be **publicly reachable** (not `127.0.0.1`). Deploy iceReach, or
> expose it with a tunnel (`cloudflared tunnel --url http://localhost:8000`).
> Set `BASE_URL` to that public URL so the webhook URL is correct.

In the same panel set **Reply-To** to an address on the reply subdomain, e.g.
`reply@reply.influenceai.in`, and **Save**. (Leave Protocol = Off — no POP/IMAP.)

---

## Option B1 — SendGrid Inbound Parse (recommended: no nameserver change)

Free, and only needs **one MX record** at GoDaddy.

1. **GoDaddy DNS** → add an MX record:
   - Host/Name: `reply`  (this is the `reply.influenceai.in` subdomain)
   - Points to: `mx.sendgrid.net`
   - Priority: `10`
2. **SendGrid** → Settings → **Inbound Parse** → *Add Host & URL*:
   - Receiving Domain: `reply.influenceai.in`
   - Destination URL: *your webhook URL from step 0*
   - (Optional) tick **POST the raw, full MIME message** — iceReach reads the
     raw `email` field; it also works with the default parsed fields.
3. Send yourself a test campaign with Reply-To = `reply@reply.influenceai.in`,
   reply to it, and within a few seconds the campaign's **Replies** ticks up.

That's it — your Zoho inbox and `team@influenceai.in` are untouched.

---

## Option B2 — Cloudflare Email Routing + Email Worker

Use this if your DNS is already on Cloudflare. Cloudflare Email Routing manages
the **zone** MX, so use a separate zone/subdomain for replies and keep Zoho's MX
on your main domain. Then bind an **Email Worker** that forwards the raw message
to the webhook:

```js
// Cloudflare Email Worker — POSTs the raw reply to the iceReach inbound webhook.
export default {
  async email(message, env, ctx) {
    const raw = await new Response(message.raw).arrayBuffer();
    await fetch(env.ICEREACH_WEBHOOK_URL, {        // set as a Worker secret/var
      method: "POST",
      headers: { "content-type": "message/rfc822" },
      body: raw,
    });
    // Optional: also forward to your real inbox so you can read replies there.
    // await message.forward("you@elsewhere.com");
  },
};
```

Set `ICEREACH_WEBHOOK_URL` to the webhook URL from step 0, route the reply
address to this Worker, and set the campaign Reply-To to that address.

---

## How matching works (and its one limit)

A reply carries the original message's `Message-ID` in its `In-Reply-To` /
`References` headers. iceReach sent that `Message-ID`, so the match is exact and
scoped to your workspace — no guessing by email address.

- **Idempotent:** at most one reply is counted per sent message, so re-delivery
  or retries never inflate the number.
- **Limit:** if a recipient *strips* those headers (rare — some web forms, or a
  brand-new email rather than a real "Reply"), it can't be matched. Normal
  "Reply" from any mail client includes them.

## Manual / scripted test

You can verify the pipeline without any provider by POSTing a raw reply yourself
(replace the token and a real sent `Message-ID`):

```bash
curl -X POST "$BASE_URL/webhooks/inbound/<token>" \
  -H "content-type: message/rfc822" \
  --data-binary $'In-Reply-To: <THE-SENT-MESSAGE-ID>\r\n\r\nyes interested'
# -> {"recorded": true}
```
