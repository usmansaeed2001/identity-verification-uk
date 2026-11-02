"""Stand-in identity provider: it always matches.

Every outcome is marked simulated, and onboarding.decision never lets a
simulated check pass an application on its own: a reviewer compares the
selfie with the ID and the Home Office photo instead. Replace this with a real
document + liveness + face match vendor before trusting it.
"""

from onboarding.enums import CheckStatus
from providers.base import CheckOutcome, IdentityResult

SIMULATED_REASON = "Simulated check: nothing was really verified. Compare the photos yourself."


class StubIdentityProvider:
    name = "identity_stub"

    def verify(self, document_type: str, document_images: list[bytes], selfie_frames: list[bytes]) -> IdentityResult:
        def outcome(**details) -> CheckOutcome:
            status = CheckStatus.PASS if document_images and selfie_frames else CheckStatus.UNCLEAR
            reasons = [SIMULATED_REASON] if status == CheckStatus.PASS else ["Photos are missing."]
            return CheckOutcome(status, reasons, {"simulated": True, "provider": self.name, **details})

        return IdentityResult(
            identity_document=outcome(document_type=document_type, images=len(document_images)),
            liveness=outcome(frames=len(selfie_frames)),
            face_match=outcome(score=1.0),
        )
