import itertools
import math
from objects import Bey, Hit

class Registry:
    def __init__(self):
        #リストの初期化
        self.frame_count:int = 0
        self.bey_list:list[list[Bey]] = [[] for _ in range(20)]
        self.hit_list:list[list[Hit]] = [[] for _ in range(20)]
        self.max_bey_id = 0
        

    def getBeyList(self) -> list[list[Bey]]:
        return self.bey_list
    

    def getHitList(self) -> list[list[Hit]]:
        return [[hit for hit in hits if hit.isNewHit()] for hits in self.hit_list]
    

    def getMessage(self) -> str:
        message = f"{self.frame_count}, beys:"
        for bey in self.bey_list[-1]:
            message += str(bey)
        message += ", hits:"
        for hit in self.hit_list[-1]:
            if hit.isNewHit():
                message += str(hit)
        return message
    

    def register(self, beys:list[Bey], hits:list[Hit]):
        for bey in beys: bey.setFrame(self.frame_count)
        self.__setBeyId(beys)
        self.bey_list.append(beys)
        self.__jadgeHits(hits)
        self.hit_list.append(hits)

        # 古いログを削除
        if(len(self.bey_list) > 20):
            self.bey_list.pop(0)
            self.hit_list.pop(0)
    

    def nextFrame(self):
        self.frame_count += 1
    

    # 新規に検出されたBeyオブジェクト（new_beys）に対して、直近のフレームの既存Beyとの距離を基に
    # マッチングし、既存BeyのIDを引き継ぐか、新たにIDを割り当てる処理を行う。
    def __setBeyId(self, new_beys: list[Bey]):
        recent_beys = self.__collectRecentBeys(frames=3) # 直近3フレーム中のbeyのリスト
        new_bey_indices = {i: bey for i, bey in enumerate(new_beys)} # 新規Beyに仮のidを割り振り
        candidate_pairs = self.__generateCandidatePairs(new_bey_indices, recent_beys)
        
        # 各ペアについて、距離が近い順にIDのマッチングを試みる
        assigned_new_indices: set[int] = set()  # 既にマッチングが完了した新規Beyのインデックス
        booked_old_ids: set[int] = set()        # 既に使用済みの既存BeyのID
        for distance, new_idx, old_bey in candidate_pairs:
            if len(assigned_new_indices) == len(new_beys):
                break
            if new_idx not in assigned_new_indices and old_bey.getId() not in booked_old_ids and distance < 1000:
                new_beys[new_idx].setPreBey(old_bey)
                assigned_new_indices.add(new_idx)
                booked_old_ids.add(old_bey.getId())
        
        # 既存Beyとのマッチングができなかった新規Beyに対しては、新規IDを割り当てる
        for i, bey in new_bey_indices.items():
            if i not in assigned_new_indices:
                self.max_bey_id += 1
                bey.setId(self.max_bey_id)


    def __collectRecentBeys(self, frames: int) -> list[Bey]:
        recent_beys = []
        # 最新のフレームから順に指定数分を調査
        for frame in range(1, frames + 1):
            for bey in self.bey_list[-frame]:
                # IDが設定済みのBeyだけを対象とする
                if hasattr(bey, 'id'):
                    recent_beys.append(bey)
        return recent_beys

    # (距離, 新規Beyのインデックス, 既存Bey) を距離順（昇順）に列挙する
    def __generateCandidatePairs(self, new_bey_indices: dict[int, Bey], recent_beys: list[Bey]) -> list[tuple[float, int, Bey]]:
        candidate_pairs = []
        # 新規Beyの各要素と、直近の既存Beyとの全組み合わせを生成
        for new_idx, new_bey in new_bey_indices.items():
            for old_bey in recent_beys:
                # 新規Beyと既存Beyの中心座標間の距離を計算
                distance = math.dist(new_bey.getPos(), old_bey.getPos())
                candidate_pairs.append((distance, new_idx, old_bey))
        # 距離が小さい順に並び替え（近いペアほど優先してマッチングを試みる）
        candidate_pairs.sort(key=lambda tup: tup[0])
        return candidate_pairs


    def __jadgeHits(self, hits:list[Hit]):
        tags = set()
        for _hits in self.hit_list[-10:]:
            for _hit in _hits:
                tags.add(_hit.getTag())
        for hit in hits:
            tag = hit.getTag()
            hit.setIsNewHit(not tag in tags) 