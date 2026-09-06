"""Group wallets that behave like one operator.

Two wallets belong together when money links them: one funded the other, they
were funded by the same non-hub address, or they both later swept funds to the
same address. Exchange hot wallets fund everyone, so any funder above
``hub_funder_threshold`` is excluded -- otherwise every retail buyer on the chain
lands in one giant "cluster".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .config import DetectorConfig
from .features import WalletActivity


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:  # path compression
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for item in self.parent:
            out[self.find(item)].append(item)
        return out


@dataclass
class Cluster:
    cluster_id: int
    members: list[str]
    reasons: list[str] = field(default_factory=list)


def build_clusters(
    activity: dict[str, WalletActivity],
    config: DetectorConfig,
    *,
    cohort: set[str] | None = None,
) -> tuple[dict[str, int], list[Cluster], set[str]]:
    """Return ``(wallet -> cluster id, clusters, hub funders)``.

    Only clusters of two or more wallets get an id; a lone wallet is not a
    cluster and should not be scored as one.
    """
    wallets = set(cohort) if cohort else set(activity)
    uf = UnionFind()
    for wallet in wallets:
        uf.add(wallet)

    funder_to_wallets: dict[str, set[str]] = defaultdict(set)
    for wallet in wallets:
        for funder in activity[wallet].funders:
            funder_to_wallets[funder].add(wallet)

    hubs = {
        funder
        for funder, members in funder_to_wallets.items()
        if len(members) > config.hub_funder_threshold
    }

    reasons: dict[frozenset[str], list[str]] = defaultdict(list)

    # Shared funder (excluding exchange-like hubs).
    for funder, members in funder_to_wallets.items():
        if funder in hubs or len(members) < 2:
            continue
        members_list = sorted(members)
        first = members_list[0]
        for other in members_list[1:]:
            uf.union(first, other)
        reasons[frozenset(members_list)].append(
            f"{len(members_list)} wallets funded by the same address {funder}"
        )

    # Direct funding between cohort wallets, and shared sweep destinations.
    sweep_targets: dict[str, set[str]] = defaultdict(set)
    for wallet in wallets:
        act = activity[wallet]
        for target in act.funded:
            if target in wallets:
                uf.union(wallet, target)
                reasons[frozenset({wallet, target})].append(
                    f"{wallet} sent gas directly to {target}"
                )
            else:
                sweep_targets[target].add(wallet)

    for target, senders in sweep_targets.items():
        if len(senders) < 2 or target in hubs:
            continue
        senders_list = sorted(senders)
        first = senders_list[0]
        for other in senders_list[1:]:
            uf.union(first, other)
        reasons[frozenset(senders_list)].append(
            f"{len(senders_list)} wallets swept funds to the same address {target}"
        )

    clusters: list[Cluster] = []
    assignment: dict[str, int] = {}
    next_id = 1
    for _, members in sorted(uf.groups().items(), key=lambda kv: -len(kv[1])):
        members = sorted(m for m in members if m in wallets)
        if len(members) < 2:
            continue
        member_set = set(members)
        cluster_reasons = [
            reason
            for key, texts in reasons.items()
            if key & member_set
            for reason in texts
        ]
        cluster = Cluster(cluster_id=next_id, members=members, reasons=sorted(set(cluster_reasons)))
        clusters.append(cluster)
        for member in members:
            assignment[member] = next_id
        next_id += 1
    return assignment, clusters, hubs
