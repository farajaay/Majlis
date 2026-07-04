import type { AuthOptions } from "next-auth";
import GitHubProvider from "next-auth/providers/github";
import { isAllowedLogin } from "./allowlist";

export const authOptions: AuthOptions = {
  providers: [
    GitHubProvider({
      clientId: process.env.GITHUB_ID || "",
      clientSecret: process.env.GITHUB_SECRET || "",
    }),
  ],
  callbacks: {
    async signIn({ profile }) {
      const login = (profile as { login?: string } | undefined)?.login;
      return isAllowedLogin(login);
    },
    async jwt({ token, profile }) {
      if (profile) token.login = (profile as { login?: string }).login;
      return token;
    },
    async session({ session, token }) {
      if (session.user) (session.user as { login?: string }).login = token.login as string;
      return session;
    },
  },
  pages: {
    signIn: "/signin",
  },
};
