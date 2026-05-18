/** /assistant/external-sites — External Sites */
import { ProviderCard } from "@/components/assistant/ProviderCard";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { externalProvidersMock } from "@/lib/assistant/mock";

export default function ExternalSitesPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-[#111827]">외부 사이트 ({externalProvidersMock.length}개)</h1>
      <ForbiddenActionBanner reason="최종 제출 / 결제 / DNS 저장 / 인증서 서명 버튼 없음" />
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {externalProvidersMock.map((provider) => (
          <ProviderCard key={provider.id} provider={provider} />
        ))}
      </div>
    </div>
  );
}
