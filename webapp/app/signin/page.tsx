"use client";
import { signIn } from "next-auth/react";

export default function SignInPage({
  searchParams,
}: {
  searchParams: { error?: string };
}) {
  return (
    <div className="signin-wrap">
      <span className="wordmark">
        <b>المجلس</b> · Majlis
      </span>
      {searchParams.error && (
        <p style={{ color: "var(--dim)" }}>
          Access denied — your GitHub account isn&apos;t seated at this council.
        </p>
      )}
      <button className="signin-btn" onClick={() => signIn("github", { callbackUrl: "/" })}>
        Sign in with GitHub
      </button>
      <a href="/guide" style={{ fontSize: 13, color: "var(--dim)" }}>
        New here? Read the guide →
      </a>
    </div>
  );
}
