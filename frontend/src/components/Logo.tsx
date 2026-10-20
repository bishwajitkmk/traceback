/** Mark: a request arrow looping back on itself — replay. */
export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <rect width="24" height="24" rx="6" fill="#0b0b0b" />
      <path d="M7 15.5V10a3 3 0 0 1 3-3h7" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      <path d="M14.5 4.5 17 7l-2.5 2.5" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="7" cy="17.5" r="1.6" fill="#2a78d6" />
    </svg>
  );
}
