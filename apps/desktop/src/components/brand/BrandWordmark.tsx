import wordmarkDark from "@/assets/ai4heor-wordmark-dark.svg";
import wordmarkLight from "@/assets/ai4heor-wordmark-light.svg";
import { useUiStore } from "@/lib/store";

interface BrandWordmarkProps {
  alt: string;
  className?: string;
  "data-testid"?: string;
}

/** Use the supplied dark-on-light and light-on-dark AI4HEOR wordmarks with
 * the app theme, including the manually selected warm theme. */
export function BrandWordmark({ alt, className, ...props }: BrandWordmarkProps) {
  const theme = useUiStore((state) => state.theme);

  return (
    <img
      src={theme === "dark" ? wordmarkDark : wordmarkLight}
      alt={alt}
      className={className}
      {...props}
    />
  );
}
