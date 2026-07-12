import "./globals.css";

export const metadata = {
  title: "Northwind Gadgets — Support",
  description: "Ask about orders, policies, and returns.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
