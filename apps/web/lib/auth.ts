import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

import { loginForm, apiFetch } from "@/lib/api";

type Me = {
  id: string;
  username: string;
  display_name: string;
  role: "admin" | "treasurer" | "analyst" | "viewer";
  entity_id: string;
};

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  providers: [
    CredentialsProvider({
      name: "用户名密码",
      credentials: {
        username: { label: "用户名", type: "text" },
        password: { label: "密码", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.username || !credentials?.password) return null;
        try {
          const { access_token } = await loginForm(
            credentials.username,
            credentials.password,
          );
          const me = await apiFetch<Me>("/api/v1/me", { token: access_token });
          return {
            id: me.id,
            name: me.display_name,
            email: me.username,
            role: me.role,
            entityId: me.entity_id,
            accessToken: access_token,
          } as never;
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        // @ts-expect-error -- extended fields
        token.accessToken = user.accessToken;
        // @ts-expect-error
        token.role = user.role;
        // @ts-expect-error
        token.entityId = user.entityId;
      }
      return token;
    },
    async session({ session, token }) {
      // @ts-expect-error
      session.accessToken = token.accessToken;
      // @ts-expect-error
      session.user.role = token.role;
      // @ts-expect-error
      session.user.entityId = token.entityId;
      return session;
    },
  },
};
