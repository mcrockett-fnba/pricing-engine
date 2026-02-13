SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE PROCEDURE [bid].[SaveLoanPricingMetrics]
(
    @pkgPurchaseId INT
)
AS
BEGIN

    WITH _loancapitalratio AS (
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
        loans.pkg_purchase_loan_id
    , loans.pkg_purchase_id
    , costToAcquire        = cofbydivision.costToAcquire
    , RequiredROE          = cofbydivision.requiredRoe/100
    , costOfFunds          = cofbydivision.costOfFunds
    , capitalRatio         = loancapitalratio.capitalRatio
    , ROA                  = croa.ROA
    , roeTargetYield       = roeTargetYield.roeTargetYield
    , roePreliminaryPrice  = roePriliminaryPrice
    , roePriceMaxItv       = roePriceMaxItv.roePriceMaxItv
    , roeCentsOnTheDollar  = roePriceMaxItv.roePriceMaxItv / loans.current_balance * 100
	, estimatedTaxRate = taxExpense.taxExpense
    INTO #loans
    FROM package.fnba.pkg_purchase_loan loans
    CROSS JOIN acqdb.fnba.cofByDivision cofbydivision
    CROSS APPLY (SELECT DATEADD(MONTH, -loans.seasoning, GETDATE())) AS note(date)
    CROSS APPLY (SELECT DATEDIFF(MONTH, loans.origination_date, loans.first_payment_date))      AS toFirstPaymentDate(inMonths)
    CROSS APPLY (SELECT DATEDIFF(MONTH, loans.origination_date, loans.next_payment_due))        AS toNextPaymentDue(inMonths)

    CROSS APPLY (
        SELECT CAST(x.date_of_rate AS DATE), x.Tnote_10_year
        FROM notedb.fnba.arm_rates x
        WHERE x.Tnote_10_year IS NOT NULL
          AND x.date_of_rate = (
                SELECT MAX(date_of_rate)
                FROM notedb.fnba.arm_rates
                WHERE Tnote_10_year IS NOT NULL
            )
    ) AS treasuryRate(dateOfRate, Tnote_10_year)

    CROSS APPLY (
        SELECT CASE 
                WHEN loans.fnba_credit_score > 0         THEN loans.fnba_credit_score
                WHEN loans.blended_recent_credit > 0     THEN loans.blended_recent_credit
                WHEN loans.credit_bor_recent > 0         THEN loans.credit_bor_recent
                WHEN loans.credit_bor_original > 0       THEN loans.credit_bor_original
                ELSE 555
               END
    ) AS credit(score)

    CROSS APPLY (
        SELECT CASE 
                WHEN loans.ltv_recent_bpo > 0            THEN loans.ltv_recent_bpo
                WHEN loans.fnba_cltv > 0                 THEN loans.fnba_cltv
                WHEN loans.seller_recent_bpo > 0         THEN loans.current_balance / loans.seller_recent_bpo
                WHEN loans.sale_price_original > 0       THEN loans.current_balance / loans.sale_price_original
                ELSE NULL
               END
    ) AS ltv(value)

	CROSS APPLY (
		SELECT CASE 
			WHEN loans.fnba_property_evaluation>0 THEN loans.fnba_property_evaluation
			WHEN loans.seller_recent_bpo>0 THEN loans.seller_recent_bpo
			WHEN loans.seller_outdated_bpo>0 THEN loans.seller_outdated_bpo
			WHEN loans.appr_value_original>0 THEN loans.appr_value_original
			ELSE loans.sale_price_original
		END
	)AS mostrecentvalue(mostrecentvalue)

    CROSS APPLY (SELECT IIF(ISNULL(loans.rate_type,'Fixed') LIKE 'F%', 'FXD', 'ARM')) AS rate(type)
    CROSS APPLY (SELECT IIF(loans.borrower_ssn LIKE '9%', 'ITIN', 'Not ITIN'))          AS itin(status)

    CROSS APPLY bid.ExpectedPrepaymentRate(
          itin.status
        , credit.score
        , loans.interest_rate_current
        , ltv.value
        , loans.current_balance
        , loans.interest_rate_current - treasuryRate.Tnote_10_year
        , loans.property_state
        , ISNULL(loans.fnba_lien_position,1)
        , rate.type
    ) expectedPrepayRate

    CROSS APPLY (
        SELECT utilities.Amortize(
              loans.current_balance
            , loans.pandi_current * expectedPrepayRate.overallAverage
            , loans.interest_rate_current
            , 12
        )
    ) AS amortization(plug)

    CROSS APPLY (
        SELECT TRY_CAST(
            utilities.PresentValue(
                  loans.pandi_current * expectedPrepayRate.overallAverage
                , IIF(loans.fnba_required_yield < 2.00, loans.fnba_required_yield/12.0, NULL)
                , amortization.plug
            ) AS DECIMAL(15, 2)
        )
    ) AS presentValue(pv)

    CROSS APPLY (
        SELECT CASE 
                WHEN presentValue.pv > loans.fnba_property_evaluation * 0.85 
                    THEN loans.fnba_property_evaluation * 0.85
                WHEN presentValue.pv > loans.current_balance * 1.05 
                    THEN loans.current_balance * 1.05 
                ELSE presentValue.pv 
               END
    ) AS purchase(price)

    CROSS APPLY (
        SELECT CASE 
                WHEN purchase.price - loans.current_balance > 10.00 THEN 'Premium'
                WHEN loans.current_balance - purchase.price > 10.00 THEN 'Discount'
                ELSE 'Par'
               END
    ) AS purchasePrice(type)

    CROSS APPLY (
        SELECT tools.finance.calculateYield(
              purchase.price
            , loans.pandi_current * expectedPrepayRate.overallAverage
            , amortization.plug
            , 12
        )
    ) AS yield(value)

    CROSS APPLY package.bid.servicingCosts(
          itin.status
        , credit.score
        , loans.interest_rate_current
        , ltv.value
        , loans.current_balance
        , loans.interest_rate_current - treasuryRate.Tnote_10_year
        , loans.property_state
        , ISNULL(loans.fnba_lien_position,1)
        , rate.type
    ) servicingCosts

    LEFT JOIN _loancapitalratio loancapitalratio
        ON credit.score BETWEEN loancapitalratio.lowerLimit 
                            AND loancapitalratio.upperLimit
       AND loancapitalratio.itinstatus = itin.status

    CROSS APPLY (SELECT cofbydivision.costOfFunds/100*(1-loancapitalratio.capitalRatio)) AS cof(costOfFunds)
    CROSS APPLY (SELECT cofbydivision.costToAcquire/amortization.plug) AS cta(costToAcquire)
    CROSS APPLY (SELECT cofbydivision.requiredRoe/100*loancapitalratio.capitalRatio) AS croa(ROA)
    CROSS APPLY (SELECT croa.ROA * cofbydivision.estimatedTaxRate/100) AS taxExpense(taxExpense)

    CROSS APPLY (
        SELECT ROA
             + cof.costOfFunds
             + servicingCosts.overallAverage
             + taxExpense
    ) AS roeTargetYield(roeTargetYield)

    CROSS APPLY (
        SELECT TRY_CAST(
            utilities.PresentValue(
                  CAST(((loans.pandi_current*expectedPrepayRate.overallAverage)-cta.costToAcquire) AS DECIMAL(15, 2))
                , IIF(roeTargetYield.roeTargetYield < 2.00, CAST(roeTargetYield.roeTargetYield/12 AS DECIMAL(10,7)), NULL)
                , amortization.plug
            ) AS DECIMAL(38, 2)
        )
    ) AS roePriliminaryPrice(roePriliminaryPrice)

    CROSS APPLY (
        SELECT CASE 
                WHEN roePriliminaryPrice / NULLIF(mostrecentvalue.mostrecentvalue,0) > 0.85
                    THEN mostrecentvalue.mostrecentvalue * .85
                WHEN roePriliminaryPrice > loans.current_balance * 1.05 
                    THEN loans.current_balance * 1.05
                ELSE roePriliminaryPrice
               END
    ) AS roePriceMaxItv(roePriceMaxItv)

    CROSS APPLY (
        SELECT tools.finance.calculateYield(
              NULLIF(roePriceMaxItv.roePriceMaxItv,0)
            , NULLIF(loans.pandi_current * expectedPrepayRate.overallAverage,0)
            , NULLIF(amortization.plug,0)
            , 12
        ) / 100
    ) AS roeFinalYield(value)

    WHERE loans.pkg_purchase_id = @pkgPurchaseId
	  AND loancapitalratio.creditBand = IIF(credit.score = 555, 'No Score' , loancapitalratio.creditBand)
      AND cofbydivision.division = 'PPD BULK';

    UPDATE a
        SET  a.costToAcquire = b.costToAcquire
           , a.expectedRoa   = b.ROA
           , a.expectedRoe   = b.RequiredROE
           , a.capitalRatio  = b.capitalRatio
		   , a.roeTargetYield = b.roeTargetYield
		   , a.roePreliminaryPrice = b.roePreliminaryPrice
		   , a.roePriceMaxItv = b.roePriceMaxItv
		   , a.roeCentsOnTheDollar = b.roeCentsOnTheDollar
		   , a.estimatedTaxRate = b.estimatedTaxRate
    FROM fnba.pkg_purchase_loan a
    JOIN #loans b
      ON b.pkg_purchase_loan_id = a.pkg_purchase_loan_id;

END;
GO