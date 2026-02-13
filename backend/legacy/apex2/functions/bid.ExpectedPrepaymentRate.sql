SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE   FUNCTION [bid].[ExpectedPrepaymentRate]
(
    @itinStatus VARCHAR(10), 
    @creditScore INT, 
    @interestRate DECIMAL(15, 7), 
    @ltv DECIMAL(15, 2), 
    @loansize INT, 
    @interestratedelta DECIMAL(15, 2), 
    @collateralstate VARCHAR(2), 
    @lienposition INT, 
    @ratetype VARCHAR(5)
)
RETURNS TABLE
AS
RETURN
(
    WITH dimensions AS
    (
        SELECT 'creditBand' AS dimension, prepaymentRateOverAll, itinStatus
        FROM bid.PrepaymentByCreditBand
        WHERE (@creditScore = 555 AND band = 'No Score') OR (@creditScore <> 555 AND @creditScore BETWEEN lowerLimit AND upperLimit)

        UNION ALL 

        SELECT 'interestRateBand', prepaymentRateOverAll, itinStatus
        FROM bid.PrepaymentByInterestRateBand
        WHERE @interestRate BETWEEN lowerLimit AND upperLimit

        UNION ALL 

		SELECT 'ltvBand', prepaymentRateOverAll, itinStatus
		FROM bid.PrepaymentByLtvBand
		WHERE CASE WHEN @ltv < 2.0 THEN @ltv * 100 ELSE @ltv END 
		BETWEEN lowerLimit AND upperLimit

        UNION ALL 

        SELECT 'loanSizeband', prepaymentRateOverAll, itinStatus
        FROM bid.PrepaymentByLoanSizeBand
        WHERE @loansize BETWEEN lowerLimit AND upperLimit

        UNION ALL 

        SELECT 'interestRateDeltaBand', prepaymentRateOverAll, itinStatus
        FROM bid.PrepaymentByInterestRateDeltaBand
        WHERE @interestratedelta BETWEEN lowerLimit AND upperLimit

        UNION ALL

        SELECT 'collateralState', prepaymentRateOverAll, itinStatus
        FROM bid.PrepaymentByCollateralState
        WHERE band = @collateralstate

        UNION ALL 

        SELECT 'lienPosition', prepaymentRateOverAll, itinStatus
        FROM bid.PrepaymentByLienPosition
        WHERE band = @lienposition

        UNION ALL 

        SELECT 'rateType', prepaymentRateOverAll, itinStatus
        FROM bid.PrepaymentByRateType
        WHERE band = @ratetype
    ),
    filtered AS (
        SELECT * FROM dimensions WHERE itinStatus = @itinStatus
    ),
    avgVal AS (
        SELECT SUM(prepaymentRateOverAll) * 1.0 / COUNT(*) AS overallAverage
        FROM filtered
    )
    SELECT 
        MAX(CASE WHEN dimension = 'creditBand' THEN prepaymentRateOverAll END) AS creditBand,
        MAX(CASE WHEN dimension = 'interestRateBand' THEN prepaymentRateOverAll END) AS interestRateBand,
        MAX(CASE WHEN dimension = 'ltvBand' THEN prepaymentRateOverAll END) AS ltvBand,
        MAX(CASE WHEN dimension = 'loanSizeband' THEN prepaymentRateOverAll END) AS loanSizeband,
        MAX(CASE WHEN dimension = 'interestRateDeltaBand' THEN prepaymentRateOverAll END) AS interestRateDeltaBand,
        MAX(CASE WHEN dimension = 'collateralState' THEN prepaymentRateOverAll END) AS collateralState,
        MAX(CASE WHEN dimension = 'lienPosition' THEN prepaymentRateOverAll END) AS lienPosition,
        MAX(CASE WHEN dimension = 'rateType' THEN prepaymentRateOverAll END) AS rateType,
        (SELECT overallAverage FROM avgVal) AS overallAverage
    FROM filtered
);
GO