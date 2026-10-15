export type IntroLanguage = "en" | "zh";

export const makeT = (language: IntroLanguage) => (english: string, chinese: string) =>
  language === "zh" ? chinese : english;

export const screenshotPath = (basePath: string, id: string, language: IntroLanguage) =>
  `${basePath}/showcase/${language === "zh" ? "zh/" : ""}${id}.jpg`;
