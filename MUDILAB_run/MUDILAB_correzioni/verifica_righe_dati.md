## 1. Validita' delle celle rispetto al grafo

Ogni cella e' confrontata con le etichette che il grafo ammette per quella variabile.

| Riga | Celle non valide |
|---|---|
| 0 | Accident='nan' |
| 1 | - |
| 2 | - |
| 3 | Accident='nan' |
| 4 | Accident='nan' |
| 5 | Age='Young', SocioEcon='Low', Mileage='TenThou', DrivingSkill='Excellent', Accident='nan' |

## 2. La riga come query, eseguita sui due lati

Bersaglio: `Accident` se la cella e' valida, altrimenti `ThisCarCost`. Le celle non valide sono escluse dall'evidenza, tranne nel tipo `intera`.

| Riga | Bersaglio | Evidenze valide | 1a evidenza usata dall'originale | backward originale | backward corretto | coherence originale | coherence corretto |
|---|---|---|---|---|---|---|---|
| 0 | ThisCarCost=Thousand | 15 | ILiCost | OK -> The probability of ThisCarCost is Thousand given the provided conditions is 0.987 | OK -> The probability of ThisCarCost is Thousand given the provided conditions is 0.987 | OK -> Evidences are compatible with a single ThisCarCost of Thousand with a probability of 0.85 | OK -> Evidences are compatible with a single ThisCarCost of Thousand with a probability of 0.99 |
| 1 | Accident=Severe | 16 | ILiCost | OK -> The probability of Accident is Severe given the provided conditions is 0.433 | OK -> The probability of Accident is Severe given the provided conditions is 0.433 | OK -> Evidences are compatible with a single Accident of Severe with a probability of 0.74 | OK -> Evidences are NOT strongly compatible with a single Accident of Severe with a probability of 0.43 |
| 2 | Accident=Moderate | 16 | ILiCost | OK -> The probability of Accident is Moderate given the provided conditions is 0.372 | OK -> The probability of Accident is Moderate given the provided conditions is 0.372 | OK -> Evidences are NOT strongly compatible with a single Accident of Moderate with a probability of 0.07 | OK -> Evidences are NOT strongly compatible with a single Accident of Moderate with a probability of 0.37 |
| 3 | ThisCarCost=Thousand | 15 | ILiCost | OK -> The probability of ThisCarCost is Thousand given the provided conditions is 0.99 | OK -> The probability of ThisCarCost is Thousand given the provided conditions is 0.99 | OK -> Evidences are compatible with a single ThisCarCost of Thousand with a probability of 0.85 | OK -> Evidences are compatible with a single ThisCarCost of Thousand with a probability of 0.99 |
| 4 | ThisCarCost=Thousand | 15 | ILiCost | OK -> The probability of ThisCarCost is Thousand given the provided conditions is 0.731 | OK -> The probability of ThisCarCost is Thousand given the provided conditions is 0.731 | OK -> Evidences are compatible with a single ThisCarCost of Thousand with a probability of 0.85 | OK -> Evidences are compatible with a single ThisCarCost of Thousand with a probability of 0.73 |
| 5 | ThisCarCost=Thousand | 11 | ILiCost | OK -> The probability of ThisCarCost is Thousand given the provided conditions is 0.064 | OK -> The probability of ThisCarCost is Thousand given the provided conditions is 0.064 | OK -> Evidences are NOT strongly compatible with a single ThisCarCost of Thousand with a probability of 0.12 | OK -> Evidences are NOT strongly compatible with a single ThisCarCost of Thousand with a probability of 0.06 |

## 3. La riga come sta, celle non valide comprese

Solo le righe che hanno almeno una cella fuori vocabolario.

| Riga | Originale | Corretto |
|---|---|---|
| 0 | OutOfBounds: [pyAgrum] Out of bound error: label 'nan' is unknown in Accident:Labelized({None\|Mild\|Moderate\|Severe}) | ValueError: Accident='nan' non e' uno stato ammesso da Accident; stati: ['None', 'Mild', 'Moderate', 'Severe'] |
| 3 | OutOfBounds: [pyAgrum] Out of bound error: label 'nan' is unknown in Accident:Labelized({None\|Mild\|Moderate\|Severe}) | ValueError: Accident='nan' non e' uno stato ammesso da Accident; stati: ['None', 'Mild', 'Moderate', 'Severe'] |
| 4 | OutOfBounds: [pyAgrum] Out of bound error: label 'nan' is unknown in Accident:Labelized({None\|Mild\|Moderate\|Severe}) | ValueError: Accident='nan' non e' uno stato ammesso da Accident; stati: ['None', 'Mild', 'Moderate', 'Severe'] |
| 5 | OutOfBounds: [pyAgrum] Out of bound error: label 'Young' is unknown in Age:Labelized({Adolescent\|Adult\|Senior}) | ValueError: Age='Young' non e' uno stato ammesso da Age; stati: ['Adolescent', 'Adult', 'Senior'] |
