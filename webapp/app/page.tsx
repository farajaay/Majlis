import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import { isAllowedLogin } from "@/lib/allowlist";
import { Transcript } from "./Transcript";

export default async function Home() {
  const session = await getServerSession(authOptions);
  const login = (session?.user as { login?: string } | undefined)?.login;
  if (!login || !isAllowedLogin(login)) redirect("/signin");
  return <Transcript me={login} />;
}
