import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'PR Review Dashboard',
  description: 'AI PR Review Agent Metrics Dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', backgroundColor: '#f5f5f5' }}>
        {children}
      </body>
    </html>
  )
}
