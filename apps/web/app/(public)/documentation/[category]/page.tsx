import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DocsLayout } from "@/components/docs/docs-layout";
import { DocsArticle } from "@/components/docs/docs-article";
import { DOCS_CATEGORIES, getDocsCategory } from "@/content/docs";

interface DocsCategoryPageProps {
  params: Promise<{ category: string }>;
}

export function generateStaticParams() {
  return DOCS_CATEGORIES.map((category) => ({ category: category.slug }));
}

export async function generateMetadata({
  params,
}: DocsCategoryPageProps): Promise<Metadata> {
  const { category: slug } = await params;
  const category = getDocsCategory(slug);
  if (!category) return { title: "Documentation" };

  return {
    title: `${category.navLabel} | Infinity Radius Documentation`,
    description: category.description,
  };
}

export default async function DocsCategoryPage({ params }: DocsCategoryPageProps) {
  const { category: slug } = await params;
  const category = getDocsCategory(slug);
  if (!category) notFound();

  return (
    <DocsLayout>
      <DocsArticle category={category} />
    </DocsLayout>
  );
}
