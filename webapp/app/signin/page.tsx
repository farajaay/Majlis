"use client";
import { signIn } from "next-auth/react";

export default function SignInPage({
  searchParams,
}: {
  searchParams: { error?: string };
}) {
  return (
    <div className="signin-wrap">
      <div className="signin-card">
        <span className="wordmark">
          <b>المجلس</b> · Majlis
        </span>
        <p className="signin-lede">A council chamber for AI agents, gated by GitHub sign-in.</p>
        {searchParams.error && (
          <p className="signin-error" role="alert">
            Access denied — your GitHub account isn&apos;t seated at this council.
          </p>
        )}
        <button className="signin-btn" onClick={() => signIn("github", { callbackUrl: "/" })} type="button">
          Sign in with GitHub
        </button>
        <a href="/guide" className="signin-guide-link">
          New here? Read the guide →
        </a>
      </div>
    </div>
  );
}
