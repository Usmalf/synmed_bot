import { useEffect } from "react";

const DEFAULT_ORIGIN = "https://synmedhealth.com";
const DEFAULT_IMAGE = `${DEFAULT_ORIGIN}/logo-removebg-preview.png`;

function setMetaAttribute(selector, attributes) {
  let element = document.head.querySelector(selector);
  if (!element) {
    element = document.createElement("meta");
    document.head.appendChild(element);
  }
  Object.entries(attributes).forEach(([key, value]) => {
    element.setAttribute(key, value);
  });
}

function setLinkAttribute(selector, attributes) {
  let element = document.head.querySelector(selector);
  if (!element) {
    element = document.createElement("link");
    document.head.appendChild(element);
  }
  Object.entries(attributes).forEach(([key, value]) => {
    element.setAttribute(key, value);
  });
}

export default function SeoMeta({
  title,
  description,
  canonicalPath = "/",
  robots = "index, follow",
  image = DEFAULT_IMAGE,
}) {
  useEffect(() => {
    const canonicalUrl = `${DEFAULT_ORIGIN}${canonicalPath}`;
    document.title = title;

    setMetaAttribute('meta[name="description"]', { name: "description", content: description });
    setMetaAttribute('meta[name="robots"]', { name: "robots", content: robots });
    setMetaAttribute('meta[property="og:title"]', { property: "og:title", content: title });
    setMetaAttribute('meta[property="og:description"]', { property: "og:description", content: description });
    setMetaAttribute('meta[property="og:url"]', { property: "og:url", content: canonicalUrl });
    setMetaAttribute('meta[property="og:image"]', { property: "og:image", content: image });
    setMetaAttribute('meta[name="twitter:title"]', { name: "twitter:title", content: title });
    setMetaAttribute('meta[name="twitter:description"]', { name: "twitter:description", content: description });
    setMetaAttribute('meta[name="twitter:image"]', { name: "twitter:image", content: image });
    setLinkAttribute('link[rel="canonical"]', { rel: "canonical", href: canonicalUrl });
  }, [canonicalPath, description, image, robots, title]);

  return null;
}
