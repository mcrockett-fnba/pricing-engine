SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE    VIEW [bid].[ApexPriceComparisonDetail]
AS

WITH _investandcapital AS (
	SELECT 
		accountnumber, 
		AVG(averageInvestment) AS avgInvestment
	FROM fnba.pkg_purchase_loan loan
	JOIN relmeom.profit.investmentAndCapital capital
	ON loan.fnba_account_number=capital.accountNumber
	GROUP BY accountnumber
),
_loancapitalratio AS (
	SELECT *,
		CASE 
			WHEN creditBand = 'No Score' THEN 555
			WHEN creditBand = '< 576' THEN 0
			WHEN creditBand = '576-600' THEN 576
			WHEN creditBand = '601-625' THEN 601
			WHEN creditBand = '626-650' THEN 626
			WHEN creditBand = '651-675' THEN 651
			WHEN creditBand = '676-700' THEN 676
			WHEN creditBand = '701-725' THEN 701
			WHEN creditBand = '726-750' THEN 726
			ELSE 751
		END AS lowerLimit,
		CASE 
			WHEN creditBand = 'No Score' THEN 555
			WHEN creditBand = '< 576' THEN 575
			WHEN creditBand = '576-600' THEN 600
			WHEN creditBand = '601-625' THEN 625
			WHEN creditBand = '626-650' THEN 650
			WHEN creditBand = '651-675' THEN 675
			WHEN creditBand = '676-700' THEN 700
			WHEN creditBand = '701-725' THEN 725
			WHEN creditBand = '726-750' THEN 750
			ELSE 1000
		END AS upperLimit
	FROM package.bid.LoanCapitalRatio
)
SELECT 
	accountNumber = loans.fnba_account_number
	, dateBooked = nm.entry_date
	, pkgPurchaseLoanId = loans.pkg_purchase_loan_id
	, pkgPurchaseId = loans.pkg_purchase_id
	, sellerLoanNumber = loans.account_number
	, noteDate = CAST(note.date AS DATE)
	, firstPaymentDate = CAST(DATEADD(MONTH, toFirstPaymentDate.inMonths, note.date) AS DATE)
	, nextPaymentDue = CAST(DATEADD(MONTH, toNextPaymentDue.inMonths, note.date) AS DATE)
	, seasoning = loans.seasoning
	, itinStatus = itin.status
	, originalBalance = loans.original_balance
	, interestRate = CAST(loans.interest_rate_current AS DECIMAL(15, 3))
	, CAST(ROUND(iandc.avgInvestment,3) AS DECIMAL(15,3)) AS avgInvestment
	, paymentAmount = loans.pandi_current
	, originalAmortization = loans.original_amortization
	, ltv = CAST(ltv.value AS DECIMAL(15, 2))
	, creditScore = credit.score
	, collateralState = loans.property_state
	, propertyType = loans.property_type
	, occupancy = loans.occupancy
	, amortizationType = rate.type
	, appraisedValue = loans.fnba_property_evaluation
	, treasuryRateDate = treasuryRate.dateOfRate
	, prepaymentRate = CAST(expectedPrepayRate.overallAverage AS DECIMAL(15, 3))
	, amortizationPlug = amortization.plug
	, originalPurchasePrice = IIF(nm.entry_date IS NOT NULL, loans.final_price_with_itv_cap, NULL)
	, newPurchasePrice = CAST(purchase.price AS DECIMAL(15, 2))
	, currentBalance = loans.current_balance
	, presentValue = presentValue.pv
	, originalCentsOnTheDollar = CAST(loans.cents_on_the_dollar AS DECIMAL(15, 2))
	, newCentsOnTheDollar = CAST(purchase.price / loans.current_balance * 100 AS DECIMAL(15, 2))
	, purchasePriceType = purchasePrice.type
	, targetYield = CAST(loans.fnba_required_yield AS DECIMAL(15, 5))
	, apexYield = CAST(yield.value / 100.0 AS DECIMAL(15, 5))
	, CAST(ROUND(loancapitalratio.capitalRatio,5) AS DECIMAL(15,5)) AS capitalRatio
	, CAST(ROUND(cofbydivision.requiredRoe/100,5) AS DECIMAL (15,5)) AS RequiredROE
	, croa.ROA
	, taxExpense.taxExpense 
	, cof.costOfFunds
	, servicingCosts = CAST(servicingCosts.overallAverage AS DECIMAL(15, 5))
	, cta.costToAcquire
	,roeTargetYield=CAST(ROUND(roeTargetYield.roeTargetYield,5)AS DECIMAL(15,5))
	,roePreliminaryPrice= CAST(ROUND(roePriliminaryPrice,5) AS DECIMAL(32,5))
	,roePriceMaxItv= CAST(ROUND(roePriceMaxItv.roePriceMaxItv,5)AS DECIMAL(32,5))
	,roeCentsOnTheDollar=CAST(ROUND(roePriceMaxItv.roePriceMaxItv/loans.current_balance*100,5)AS DECIMAL(32,5))
	,roeFinalYield=CAST(ROUND(roeFinalYield.value,5) AS DECIMAL(15,5))
	,ROEmodelPriceIncrease = CAST(ROUND(roePriceMaxItv.roePriceMaxItv/loans.current_balance*100,5)AS DECIMAL(32,5)) - CAST(loans.cents_on_the_dollar AS DECIMAL(15, 2))
FROM package.fnba.pkg_purchase_loan loans
LEFT JOIN notedb.fnba.note_master nm
	ON nm.account_number = loans.fnba_account_number
LEFT JOIN notedb.fnba.note_status ns
	ON ns.note_status_id = nm.note_status_id
LEFT JOIN _investandcapital iandc
	ON iandc.accountNumber=loans.fnba_account_number
CROSS JOIN acqdb.fnba.cofByDivision cofbydivision
CROSS APPLY(SELECT DATEADD(MONTH, -loans.seasoning, GETDATE())) AS note(date)
CROSS APPLY(SELECT DATEDIFF(MONTH, loans.origination_date, loans.first_payment_date)) AS toFirstPaymentDate(inMonths)
CROSS APPLY(SELECT DATEDIFF(MONTH, loans.origination_date, loans.next_payment_due)) AS toNextPaymentDue(inMonths)
CROSS APPLY (SELECT CAST(x.date_of_rate AS DATE),x.Tnote_10_year
				FROM notedb.fnba.arm_rates x
				WHERE x.Tnote_10_year IS NOT NULL
				AND x.date_of_rate = (SELECT MAX(date_of_rate) FROM notedb.fnba.arm_rates WHERE Tnote_10_year IS NOT NULL))
				AS treasuryRate(dateOfRate, Tnote_10_year)
CROSS APPLY (SELECT CASE 
						WHEN loans.fnba_credit_score > 0 THEN loans.fnba_credit_score
						WHEN loans.blended_recent_credit > 0 THEN loans.blended_recent_credit
						WHEN loans.credit_bor_recent > 0 THEN loans.credit_bor_recent
						WHEN loans.credit_bor_original > 0 THEN loans.credit_bor_original
						ELSE 555
					END) AS credit(score)
CROSS APPLY (SELECT CASE 
						WHEN loans.ltv_recent_bpo>0 THEN loans.ltv_recent_bpo
						WHEN loans.fnba_cltv > 0 THEN loans.fnba_cltv
						WHEN loans.seller_recent_bpo > 0 THEN loans.current_balance/loans.seller_recent_bpo
						WHEN loans.sale_price_original > 0 THEN loans.current_balance/loans.sale_price_original
						ELSE NULL
					END) AS ltv(value)
CROSS APPLY (SELECT IIF(ISNULL(loans.rate_type,'Fixed') LIKE('F%'), 'FXD', 'ARM')) AS rate(type)
CROSS APPLY(SELECT IIF(loans.borrower_ssn LIKE('9%'), 'ITIN', 'Not ITIN')) AS itin(status)
CROSS APPLY bid.ExpectedPrepaymentRate(itin.status, 
											credit.score,
												loans.interest_rate_current,
												ltv.value,
												loans.current_balance, 
												loans.interest_rate_current - treasuryRate.Tnote_10_year,
												loans.property_state,
												ISNULL(loans.fnba_lien_position,1),
												rate.type) expectedPrepayRate
CROSS APPLY(SELECT utilities.Amortize(loans.current_balance, 
							   loans.pandi_current * expectedPrepayRate.overallAverage, 
							   loans.interest_rate_current, 
							   12)) AS amortization(plug)
CROSS APPLY(SELECT TRY_CAST(utilities.PresentValue(loans.pandi_current * expectedPrepayRate.overallAverage, 
												   IIF(loans.fnba_required_yield < 2.00, loans.fnba_required_yield/12.0, NULL), 
												   amortization.plug) AS DECIMAL(15, 2))) AS presentValue(pv)
CROSS APPLY(SELECT CASE WHEN presentValue.pv > loans.fnba_property_evaluation * 0.80 THEN loans.fnba_property_evaluation * 0.80
						WHEN presentValue.pv > loans.current_balance * 1.05 THEN loans.current_balance * 1.05 
					    ELSE presentValue.pv 
					    END) AS purchase(price)
CROSS APPLY(SELECT CASE WHEN purchase.price - loans.current_balance > 10.00 THEN 'Premium'
                        WHEN loans.current_balance - purchase.price > 10.00 THEN 'Discount'
                        ELSE 'Par'
                        END) AS purchasePrice(type)
CROSS APPLY(SELECT tools.finance.calculateYield(purchase.price,
												loans.pandi_current * expectedPrepayRate.overallAverage, 
												amortization.plug,
												12)) AS yield(value)
CROSS APPLY package.bid.servicingCosts(itin.status, 
									credit.score,
									loans.interest_rate_current,
									ltv.value,
									loans.current_balance, 
									loans.interest_rate_current - treasuryRate.Tnote_10_year,
									loans.property_state,
									ISNULL(loans.fnba_lien_position,1),
									rate.type)servicingCosts
LEFT JOIN _loancapitalratio loancapitalratio 
	 ON credit.score BETWEEN loancapitalratio.lowerLimit AND loancapitalratio.upperLimit
	 AND loancapitalratio.itinstatus= itin.status
CROSS APPLY (SELECT CAST(ROUND(cofbydivision.costOfFunds/100*(1-loancapitalratio.capitalRatio),5) AS DECIMAL (15,5))) AS cof(costOfFunds)
CROSS APPLY (SELECT CAST(ROUND(cofbydivision.costToAcquire/4/iandc.avgInvestment,5) AS DECIMAL (15,5))) AS cta(costToAcquire)
CROSS APPLY (SELECT CAST(ROUND(cofbydivision.requiredRoe/100*loancapitalratio.capitalRatio,5) AS DECIMAL (15,5))) AS croa(ROA)
CROSS APPLY (SELECT CAST(croa.roa*cofbydivision.estimatedTaxRate/100 AS DECIMAL(15,5))) AS taxExpense(taxExpense)
CROSS APPLY(SELECT ROA
					+ cof.costOfFunds
					+ cta.costToAcquire
					+ servicingCosts.overallAverage
					+ taxExpense) AS roeTargetYield(roeTargetYield)
CROSS APPLY(SELECT TRY_CAST(utilities.PresentValue(CAST((loans.pandi_current*expectedPrepayRate.overallAverage) AS DECIMAL(15, 2)),
												IIF(roeTargetYield.roeTargetYield < 2.00, CAST(roeTargetYield.roeTargetYield/12 AS DECIMAL(10, 7)), NULL),
												   amortization.plug) AS DECIMAL(38, 2)))AS roePriliminaryPrice(roePriliminaryPrice)
CROSS APPLY(SELECT CASE WHEN roePriliminaryPrice/NULLIF(loans.appr_value_original,0)>.80 THEN loans.appr_value_original*.80
					WHEN roePriliminaryPrice>loans.current_balance * 1.05 THEN loans.current_balance * 1.05
					ELSE roePriliminaryPrice
					END) AS roePriceMaxItv(roePriceMaxItv)
CROSS APPLY(SELECT tools.finance.calculateYield(NULLIF(roePriceMaxItv.roePriceMaxItv,0),
												NULLIF(loans.pandi_current * expectedPrepayRate.overallAverage,0), 
												NULLIF(amortization.plug,0),
												12)/100) AS roeFinalYield(value)
WHERE loans.fnba_property_evaluation > 0.00
 AND loancapitalratio.creditBand = IIF(credit.score = 555, 'No Score' , loancapitalratio.creditBand)
	AND loans.current_balance > 0.00
	AND purchase.price > 0.00
	AND nm.entry_date IS NOT NULL 
	AND cofbydivision.division='PPD BULK'
GO