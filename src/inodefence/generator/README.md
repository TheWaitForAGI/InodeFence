# 초기 case 생성

## 책임과 API

`minimal_seed_corpus() -> tuple[ArchiveCase, ...]`는 작고 정상적인 네 시작 case를 반환한다.
순서는 regular file → directory/file → regular/hardlink → regular/symlink다. 고정 raw path,
content(`b"hello inodefence"`)와 mode를 사용하고 link target은 먼저 나온 `a.txt`다.
기존 개발 fixture의 logical cases와 TAR bytes를 유지한다. Return 값과 entries는 immutable다.

```python
from inodefence.campaign import CampaignConfig, run_campaign
from inodefence.generator import minimal_seed_corpus
from inodefence.targets import PythonTarfileTarget

result = run_campaign(minimal_seed_corpus(), PythonTarfileTarget(), CampaignConfig(11, 25))
```

Generator는 표준 library와 canonical archive model만 의존한다. Filesystem/RNG access,
feedback/pipeline/target dependency, TAR byte serialization과 CVE recipe는 없다. Campaign은
계속 initial cases를 명시적으로 받으며 이 API를 자동으로 호출하거나 default seed를 고르지 않는다.

[Fixture script](../../../scripts/generate_tar_fixtures.py)의 `baseline_case`는 이 API에 위임한다.
Builder가 TAR encoding을, Mutator가 기존 case 변형을 담당한다. 모듈 경계는
[architecture](../../../docs/research/design/architecture.md)를 따른다. 이 corpus의 연구 효과나
benchmark 적합성은 아직 평가하지 않았다.
