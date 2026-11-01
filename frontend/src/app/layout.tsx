import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' });
const jetbrains = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono' });

export const metadata: Metadata = {
  title: 'DocGuard — Documentation Drift Detection',
  description: 'Prevent documentation drift before code merges.',
  icons: {
    icon: '/assets/images/JGaMQVbj6Yq5XKUGmslLRGu5w8s.png',
    apple: '/assets/images/JGaMQVbj6Yq5XKUGmslLRGu5w8s.png',
  },
  openGraph: {
    title: 'DocGuard — Documentation Drift Detection',
    description: 'Catch the documentation a pull request made wrong.',
    images: ['/assets/images/JGaMQVbj6Yq5XKUGmslLRGu5w8s.png'],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${jetbrains.variable} font-sans bg-background text-ink min-h-screen`}>
        {children}
      </body>
    </html>
  );
}

