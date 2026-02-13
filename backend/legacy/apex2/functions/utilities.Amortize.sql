SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE   FUNCTION [utilities].[Amortize](@presentValue DECIMAL(15, 2), @paymentAmount DECIMAL(15, 2), @rate DECIMAL(15, 7), @ppy INT)
RETURNS INT
AS

BEGIN

RETURN CEILING(IIF(@rate > 0 AND @paymentAmount > 0 AND @ppy > 0 AND @presentValue * (@rate / @ppy / 100) / @paymentAmount < 1,
					-LOG((1 - (@presentValue * (@rate / @ppy / 100) / @paymentAmount))) / LOG(1 + (@rate / @ppy / 100)),
					NULL
				 )
			  )
END
GO