import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import basePreset from "@infinity-radius/config/eslint-preset";

const eslintConfig = [...basePreset, ...nextCoreWebVitals];

export default eslintConfig;
