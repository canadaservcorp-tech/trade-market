# Bot de pratique « micro » : argent fictif, 50 $

**Aucun ordre réel.** Ce dossier ne touche ni à IBKR, ni à `ibkr.py`, ni à `ib_async`, ni au bot réel
(`bot.py`, `bot2.py`, `config.py`). Les prix viennent de yfinance seulement. Les achats et les ventes
sont seulement écrits dans un fichier.

## L'idée, en simple

On part de **50 $ fictifs** (CAD) et on a **au plus 2 positions de 25 $**. Chaque ordre (achat ou
vente) coûte **1,00 $**, comme le minimum chez IBKR Canada. On simule des actions fractionnées.

- **Achat** : quand un titre est au moins **X = 5 %** sous son plus haut des **N = 10** derniers jours de bourse.
  Si plusieurs titres baissent en même temps, on prend la plus forte baisse en premier.
- **Vente**, selon la première condition remplie :
  - **+Y = 8 %** : objectif atteint ;
  - **−Z = 8 %** : arrêt de perte ;
  - **D = 15** jours de bourse : on sort de toute façon.

On surveille 10 titres très liquides : XIU, XIC, VFV, ZEB, XEQT (TSX), ainsi que SPY, QQQ, IWM, AAPL
et MSFT (US). Les prix US sont convertis en CAD avec `CAD=X`. Tous les réglages sont dans
`micro_config.py`.

## Résultat du backtest (2 ans de données journalières, jusqu'au 2026-11-23)

Commande : `python micro_backtest.py`. Ce sont des chiffres historiques. Les vôtres changeront un peu
d'un jour à l'autre.

**Comment on a choisi X, Y et Z sans tricher** : on a testé 36 combinaisons (X ∈ {2, 3, 5},
Y ∈ {2, 3, 5, 8}, Z ∈ {3, 5, 8}) **sur la 1re année seulement**. La meilleure, X=5 / Y=8 / Z=8, a ensuite
été vérifiée sur la **2e année**, que la grille n'avait jamais vue.

| Période | Trades | Gagnants | Profit net (frais 1 $) | Profit net si frais = 0 | Garder XEQT.TO |
|---|---|---|---|---|---|
| Année 1 (choix de la règle) | 14 | 21 % | **−28,56 $** (−57 %) | +0,05 $ | +6,36 $ (+12,7 %) |
| Année 2 (vérification) | 20 | 0 % | **−38,60 $** (−77 %) | +10,15 $ (+20 %) | +4,03 $ (+8,1 %) |
| Les 2 ans d'affilée | 21 | 14 % | **−45,34 $** (−91 %) | +12,61 $ (+25 %) | +14,27 $ (+28,5 %) |

Ce qu'on en retient :

1. **Les frais rendent la stratégie perdante.** Sur une position de 25 $, un aller-retour coûte 2 $, soit
   **8 %**. Une vente à +8 % ne fait donc que payer les frais. C'est pour ça qu'il y a 0 % de gagnants
   à l'année 2, même si la règle gagnait +20 % quand les frais sont à zéro.
2. **Les 36 combinaisons perdent toutes de l'argent avec les frais.** La « meilleure » est seulement
   celle qui perd le moins.
3. **Garder XEQT.TO** (un seul achat, une seule vente) fait mieux sur chaque période.
4. Pour que ce genre de stratégie ait une chance, il faudrait des positions beaucoup plus grosses
   (avec 2 500 $, le même 2 $ de frais ne représente plus que 0,08 %) ou un courtier sans frais.

> **Important : 50 $ ne peuvent pas rapporter 1000 $ par mois.** Il faudrait gagner 2000 % *par mois*.
> Même une très bonne année (+10 %) rapporte environ 5 $ **par an** sur 50 $. Ce bot sert à
> **apprendre et observer** sans risque. Ce n'est pas un moyen de faire de l'argent.

## Utilisation

```
run_micro.bat              une passe : lit les prix, applique la règle (ne fait rien si la bourse est fermée)
run_micro.bat --force      une passe même hors des heures de marché
run_micro.bat --rapport    affiche le rapport
schedule_micro.bat         crée la tâche Windows (toutes les 30 min, lun-ven 9 h 30-16 h)
schedule_micro.bat remove  supprime la tâche
```

`schedule_micro.bat` utilise l'heure **locale** du PC. Il faut donc que le PC soit à l'heure de
Montréal (Est).

Fichiers créés à l'exécution (ignorés par git) :

- `paper_micro.csv` : un achat ou une vente fictifs par ligne ;
- `paper_state.json` : le cash et les positions ouvertes ;
- `micro_paper.log` : le journal de chaque passe.

Pour **repartir à zéro**, supprimez `paper_state.json` et `paper_micro.csv`.

## Comment lire le rapport (`--rapport`)

```
Capital de départ : 50.00 $
Cash              : 0.00 $                  <- argent fictif pas investi
Positions ouvertes :
  MSFT  0.0334 @ 717.58 -> 717.62 $  valeur 24.00 $ (+0.01 %)  depuis 2026-11-23
         quantité  prix d'achat  prix actuel (CAD)  valeur actuelle  variation
Valeur si on vendait tout maintenant (frais inclus) : 46.00 $
PROFIT NET après frais : -4.00 $ (-7.99 %)  <- le chiffre qui compte
Frais payés jusqu'ici   : 2.00 $
Trades :                                    <- chaque achat/vente fictif, avec le profit net des ventes
```

Le **profit net** compte tous les frais déjà payés, plus le 1 $ qu'il faudrait payer pour vendre
chaque position encore ouverte. Juste après deux achats, il est donc déjà à **−4 $**, même si les prix
n'ont pas bougé.

## Note technique

Sur ce PC, le contrôle des applications de Windows bloque la DLL de numpy 2.5. `run_micro.bat`
installe donc les versions du `requirements.txt` du projet (pandas 2.2.2, numpy < 2.1,
yfinance 0.2.66).
