# City Care Clinic staff portal

The web app for clinic staff (SPEC §17). Admins see an overview, all appointments, and edit
doctors, doctor logins, the clinic information the chatbot answers from, closures, and a read-only
database view. Doctors see their own appointments, update visit details and record consultations
(with follow-up). It talks to the FastAPI backend over plain HTTPS + JSON under `/staff`; it shares
nothing with the patient chat widget in `web/`.

React + Vite + TypeScript, no router or UI library (hash routes, plain CSS).
`src/api/client.ts` is the only module that calls `fetch`.

## Run locally

```sh
cd admin
npm install
npm run dev        # http://localhost:5174
```

The backend must be running on port 8000. The default `STAFF_ORIGINS` already
allows `http://localhost:5174` (CORS for the portal).

Other scripts: `npm run build`, `npm run typecheck`, `npm run lint`, `npm run format`,
`npm test`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Backend base URL (see `.env.example`) |

## First login

There is no sign-up. The first admin account is created by the backend at startup from
`ADMIN_EMAIL` and `ADMIN_PASSWORD` (or with the `clinic-create-admin` CLI). Sign in with those,
then create doctor logins under **Accounts**.

## Deploy on Vercel

1. Create a new Vercel project from this repository (separate from the widget project).
2. Root directory: `admin`. Framework preset: Vite.
3. Set `VITE_API_URL` to the Render backend URL, for example `https://clinic-bot.onrender.com`.
4. Deploy, then add the Vercel URL (for example `https://clinic-staff.vercel.app`) to
   `STAFF_ORIGINS` on Render and redeploy the backend.

Routing uses the URL hash (`#/admin/overview`), so no rewrite rules are needed.
